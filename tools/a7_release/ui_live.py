from __future__ import annotations

import argparse
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

from analyzazprav.normalization import CanonicalDatabase
from analyzazprav.runtime import RuntimeValidationError, compile_packet_to_packs
from a6.attachments import load_attachment_sources, load_message_attachments
from a6.data import analysis_packet, load_sqlite_messages
from a6.evidence import enrich_analysis_packet_source_provenance
from a6.provenance import load_message_sources
from tools.a7_release.a6_live import _build_database
from tools.a7_release.common import finalize, issue, write_report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True)
    parser.add_argument("--contract-sha", required=True)
    args = parser.parse_args()

    checks: dict[str, object] = {}
    issues: list[dict[str, str]] = []

    with TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "messages.sqlite"
        c1, _c2, shared = _build_database(db_path)
        frame, info = load_sqlite_messages(db_path)
        checks["authoritative_canonical_view"] = info.object_name == "analysis_messages"
        if checks["authoritative_canonical_view"] is not True:
            issues.append(issue("ERROR", "UI_NONAUTHORITATIVE_READ_MODEL", str(info.object_name)))

        db = CanonicalDatabase(db_path)
        expected_memberships = {
            str(row["membership_id"])
            for row in db.conn.execute("SELECT membership_id FROM analysis_messages").fetchall()
        }
        actual_memberships = set(frame["membership_id"].astype(str))
        checks["membership_set_exact"] = expected_memberships == actual_memberships
        checks["membership_count"] = len(actual_memberships)
        checks["unknown_timestamp_memberships"] = int(frame["timestamp"].isna().sum())
        if checks["membership_set_exact"] is not True:
            issues.append(issue("ERROR", "UI_MEMBERSHIP_SET_MISMATCH", "canonical read model"))
        if checks["unknown_timestamp_memberships"] != 1:
            issues.append(issue("ERROR", "UI_UNKNOWN_TIMESTAMP_LOSS", "expected one unknown timestamp"))

        selected_id = str(shared)
        conversation = frame[frame["conversation_id"].astype(str) == str(c1)].reset_index(drop=True)
        base_packet = analysis_packet(conversation, [selected_id], context_before=0, context_after=0)
        packet = enrich_analysis_packet_source_provenance(base_packet, db_path)
        checks["packet_source_provenance_status"] = packet.get("source_provenance_status")

        try:
            packs = compile_packet_to_packs(packet, max_input_chars=6000)
        except Exception as exc:
            issues.append(issue("ERROR", "UI_RUNTIME_PACK_FAILED", type(exc).__name__))
            packs = ()

        checks["runtime_pack_count"] = len(packs)
        if len(packs) == 1:
            selected_items = [item for item in packs[0].items if item.message_id == selected_id]
            checks["selected_item_count"] = len(selected_items)
            if len(selected_items) == 1:
                item = selected_items[0]
                packet_row = next(
                    row for row in packet["messages"] if str(row["message_id"]) == selected_id
                )
                checks["runtime_membership_preserved"] = item.membership_id == str(packet_row["membership_id"])
                checks["runtime_source_records_preserved"] = list(item.source_record_keys) == packet_row["source_record_keys"]
                checks["runtime_source_snapshots_preserved"] = list(item.source_snapshot_keys) == packet_row["source_snapshot_keys"]
                provider_item = next(
                    raw for raw in packs[0].provider_payload()["evidence"] if raw["label"] == item.label
                )
                checks["provider_payload_hides_canonical_identity"] = (
                    "message_id" not in provider_item
                    and "membership_id" not in provider_item
                    and "source_record_keys" not in provider_item
                )
            else:
                checks["runtime_membership_preserved"] = False
                checks["runtime_source_records_preserved"] = False
                checks["runtime_source_snapshots_preserved"] = False
                checks["provider_payload_hides_canonical_identity"] = False
        else:
            checks["selected_item_count"] = 0
            checks["runtime_membership_preserved"] = False
            checks["runtime_source_records_preserved"] = False
            checks["runtime_source_snapshots_preserved"] = False
            checks["provider_payload_hides_canonical_identity"] = False

        for name in (
            "runtime_membership_preserved",
            "runtime_source_records_preserved",
            "runtime_source_snapshots_preserved",
            "provider_payload_hides_canonical_identity",
        ):
            if checks[name] is not True:
                issues.append(issue("ERROR", "UI_RUNTIME_EVIDENCE_CONTRACT_FAILED", name))

        source_rows = load_message_sources(db_path, [selected_id])
        attachment_rows = load_message_attachments(db_path, [selected_id])
        occurrence_ids = list(attachment_rows["occurrence_id"].astype(str))
        attachment_source_rows = load_attachment_sources(db_path, occurrence_ids)
        checks["message_source_rows_visible"] = len(source_rows) >= 1
        checks["attachment_occurrence_count"] = len(attachment_rows)
        checks["attachment_source_count"] = len(attachment_source_rows)
        if len(source_rows) < 1 or len(attachment_rows) != 1 or len(attachment_source_rows) != 1:
            issues.append(issue("ERROR", "UI_PROVENANCE_PROJECTION_LOSS", "message/attachment provenance"))

        corrupted = deepcopy(packet)
        corrupted["messages"][0]["source_record_keys"] = []
        rejected = False
        try:
            compile_packet_to_packs(corrupted, max_input_chars=6000)
        except RuntimeValidationError:
            rejected = True
        checks["negative_missing_source_provenance_rejected"] = rejected
        if not rejected:
            issues.append(issue("ERROR", "UI_NEGATIVE_PROVENANCE_PROBE_FAILED", "corrupt packet accepted"))
        db.close()

    report = finalize("ui", checks, issues, contract_sha=args.contract_sha)
    write_report(report, args.report)
    return 0 if report["verdict"] == "VALID" else 1


if __name__ == "__main__":
    raise SystemExit(main())
