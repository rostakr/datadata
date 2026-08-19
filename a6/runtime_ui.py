from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pandas as pd
import streamlit as st

from a6.a5_bridge import (
    RuntimeUnavailable,
    check_local_runtime_provider,
    run_local_runtime,
    runtime_available,
)
from a6.data import (
    DataSourceError,
    SourceInfo,
    add_opposite_sender_gap,
    analysis_packet,
    demo_messages,
    filter_messages,
    load_sqlite_messages,
)
from a6.evidence import (
    FAIL,
    PASS,
    STALE,
    UNVERIFIED,
    PacketProvenanceError,
    enrich_analysis_packet_source_provenance,
    load_current_message_provenance,
    reconcile_a5_evidence_ref,
)
from a6.findings import empty_findings, filter_findings, load_a4_findings, resolve_evidence
from a6.local_runtime import configured_database
from a6.responsive import install_responsive_contract
from analyzazprav.runtime import RuntimeValidationError, compile_packet_to_packs

st.set_page_config(page_title="Analýza zpráv", page_icon="💬", layout="wide")


@st.cache_data(show_spinner=False)
def _load_db(path: str):
    messages, info = load_sqlite_messages(path)
    findings = load_a4_findings(path)
    return messages, info, findings


def _source() -> tuple[pd.DataFrame, SourceInfo, pd.DataFrame, str | None]:
    configured = configured_database()
    if configured is not None:
        try:
            messages, info, findings = _load_db(str(configured))
        except DataSourceError as exc:
            st.error(str(exc))
            st.stop()
        return messages, info, findings, str(configured)

    st.sidebar.header("Zdroj dat")
    if st.sidebar.radio("Režim", ["Demo", "SQLite"], horizontal=True) == "Demo":
        return demo_messages(), SourceInfo("demo", "Vestavěná demo data"), empty_findings(), None

    path = st.sidebar.text_input("SQLite", "database/messages.sqlite").strip()
    try:
        messages, info, findings = _load_db(path)
    except DataSourceError as exc:
        st.sidebar.error(str(exc))
        st.stop()
    return messages, info, findings, path


def _duration(value: Any) -> str:
    if value is None or pd.isna(value):
        return "—"
    seconds = float(value)
    if seconds < 60:
        return f"{seconds:.0f} s"
    if seconds < 3600:
        return f"{seconds / 60:.1f} min"
    if seconds < 86400:
        return f"{seconds / 3600:.1f} h"
    return f"{seconds / 86400:.1f} d"


def _conversation_selector(frame: pd.DataFrame) -> tuple[str, pd.DataFrame]:
    rows = []
    for conversation_id, group in frame.groupby("conversation_id", sort=False, dropna=False):
        contact = str(group.iloc[0].contact or conversation_id)
        rows.append((str(conversation_id), contact, int(group.message_id.nunique())))
    rows.sort(key=lambda item: (item[1].lower(), item[0]))
    labels = {
        conversation_id: f"{contact} · {count:,} zpráv"
        for conversation_id, contact, count in rows
    }
    selected = st.sidebar.selectbox(
        "Konverzace",
        [row[0] for row in rows],
        format_func=lambda value: labels.get(value, value),
    )
    return selected, frame[frame.conversation_id.astype(str) == str(selected)].reset_index(drop=True)


def _period_filter(conversation: pd.DataFrame) -> tuple[pd.DataFrame, pd.Timestamp | None, pd.Timestamp | None]:
    known = conversation.timestamp.dropna()
    start: pd.Timestamp | None = None
    end: pd.Timestamp | None = None
    if not known.empty:
        lo = known.min().date()
        hi = known.max().date()
        value = st.sidebar.date_input("Období", (lo, hi), min_value=lo, max_value=hi)
        if not isinstance(value, tuple) or len(value) != 2:
            value = (value, value)
        start = pd.Timestamp(value[0])
        end = pd.Timestamp(value[1]) + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)

    search = st.sidebar.text_input("Hledat v textu").strip()
    filtered = filter_messages(
        conversation,
        start=start,
        end=end,
        search=search or None,
        include_unknown_timestamps=True,
    )
    return filtered, start, end


def _metric_row(filtered: pd.DataFrame, signal_count: int) -> None:
    gaps = add_opposite_sender_gap(filtered)
    samples = pd.to_numeric(gaps.opposite_sender_gap_seconds, errors="coerce").dropna()
    median_gap = samples.median() if not samples.empty else None
    columns = st.columns(6)
    columns[0].metric("Memberships", f"{len(filtered):,}")
    columns[1].metric("Canonical zprávy", f"{filtered.message_id.nunique():,}")
    columns[2].metric("Aktivní dny", f"{filtered.timestamp.dt.date.nunique():,}")
    columns[3].metric("Odesílatelé", f"{filtered.sender.nunique():,}")
    columns[4].metric("Medián změny odesílatele", _duration(median_gap))
    columns[5].metric("Signály", f"{signal_count:,}")


def _message_table(frame: pd.DataFrame, *, limit: int = 1000) -> None:
    if frame.empty:
        st.info("Bez zpráv pro zvolený filtr.")
        return
    display = frame.tail(limit)[["timestamp", "sender", "text"]].copy()
    if len(frame) > limit:
        st.caption(f"Zobrazeno posledních {limit:,} z {len(frame):,} řádků. Pro menší výběr použijte období nebo hledání.")
    st.dataframe(display, use_container_width=True, hide_index=True)


def _signal_table(findings: pd.DataFrame) -> None:
    if findings.empty:
        st.info("Pro tento výběr nejsou dostupné deterministické signály.")
        return
    display = findings.copy()
    display["evidence_count"] = display.evidence_message_ids.map(len)
    st.dataframe(
        display[["finding_type", "label", "start_timestamp", "end_timestamp", "score", "evidence_count"]],
        use_container_width=True,
        hide_index=True,
    )


def _signal_picker(findings: pd.DataFrame, conversation: pd.DataFrame) -> None:
    if findings.empty:
        return
    options = list(range(len(findings)))

    def label(index: int) -> str:
        row = findings.iloc[index]
        when = "čas neznámý" if pd.isna(row.start_timestamp) else pd.Timestamp(row.start_timestamp).strftime("%Y-%m-%d")
        return f"{row.label} · {when} · score {float(row.score):.2f}"

    selected_index = st.selectbox("Signál pro interpretaci", options, format_func=label)
    row = findings.iloc[selected_index]
    ids = [str(value) for value in row.evidence_message_ids]
    evidence, missing = resolve_evidence(conversation, ids)
    if missing:
        st.error("Signal evidence obsahuje nedostupné canonical message IDs.")
    if not evidence.empty:
        with st.expander(f"Evidence signálu · {len(evidence)} zpráv"):
            _message_table(evidence, limit=200)
    if st.button("Použít tento signál pro interpretaci", type="primary"):
        st.session_state.runtime_selected_ids = ids
        st.session_state.runtime_selection_source = f"signal:{row.label}"
        st.success(f"Vybráno {len(ids)} evidence zpráv.")


def _manual_picker(filtered: pd.DataFrame) -> None:
    candidates = filtered[filtered.timestamp.notna()].tail(500).copy()
    if candidates.empty:
        st.info("V aktuálním filtru nejsou zprávy se známým časem pro ruční výběr.")
        return
    by_id = {str(row.message_id): row for row in candidates.itertuples(index=False)}
    options = list(by_id)

    def label(message_id: str) -> str:
        row = by_id[message_id]
        text = str(row.text).replace("\n", " ")
        if len(text) > 90:
            text = text[:87] + "…"
        when = pd.Timestamp(row.timestamp).strftime("%Y-%m-%d %H:%M")
        return f"{when} · {row.sender}: {text}"

    chosen = st.multiselect(
        "Ruční evidence",
        options,
        format_func=label,
        key="runtime_manual_selection",
        help="Nabízí se nejvýše posledních 500 zpráv aktuálního filtru.",
    )
    if st.button("Použít ruční výběr", disabled=not chosen):
        st.session_state.runtime_selected_ids = list(chosen)
        st.session_state.runtime_selection_source = "manual"
        st.success(f"Vybráno {len(chosen)} zpráv.")


def _build_packet(
    conversation: pd.DataFrame,
    selected_ids: list[str],
    *,
    db_path: str | None,
    radius: int,
) -> dict[str, Any]:
    packet = analysis_packet(
        conversation,
        selected_ids,
        context_before=radius,
        context_after=radius,
    )
    return enrich_analysis_packet_source_provenance(
        packet,
        db_path,
        require_provenance=db_path is not None,
    )


def _render_reconciliation(evidence_ref: Mapping[str, Any], conversation: pd.DataFrame, db_path: str | None) -> None:
    ids = [str(value) for value in evidence_ref.get("message_ids") or []]
    evidence, missing = resolve_evidence(conversation, ids)
    if missing:
        st.error("Výsledek odkazuje na canonical zprávu, která už není v aktuálním read modelu.")
    if db_path is not None and ids:
        try:
            sources = load_current_message_provenance(db_path, ids)
            current_rows = evidence[["membership_id", "message_id", "conversation_id"]].to_dict("records")
            reconciliation = reconcile_a5_evidence_ref(evidence_ref, current_rows, sources)
        except PacketProvenanceError as exc:
            st.error(f"Provenance nelze ověřit: {exc}")
        else:
            if reconciliation.status == PASS:
                st.success("Evidence odpovídá aktuální canonical membership/source provenance.")
            elif reconciliation.status == STALE:
                st.warning("Evidence je STALE vůči aktuální source provenance.")
            elif reconciliation.status == FAIL:
                st.error("Evidence nelze svázat s aktuální canonical membership/source provenance.")
            elif reconciliation.status == UNVERIFIED:
                st.warning("Evidence nelze nezávisle ověřit.")
    if not evidence.empty:
        _message_table(evidence, limit=200)


def _render_runtime_result(result: Mapping[str, Any], conversation: pd.DataFrame, db_path: str | None) -> None:
    if result.get("status") != "COMPLETED":
        st.error(str(result.get("status") or "Interpretace selhala."))
        return
    st.markdown("### Výsledek")
    st.caption(
        f"Runtime v2 · {result.get('provider')} / {result.get('model')} · "
        f"{result.get('pack_count')} evidence packů"
    )
    st.write(str(result.get("summary") or ""))
    st.caption("Shrnutí je orientační syntéza; auditovatelná evidence je uvedena u jednotlivých claimů níže.")

    for index, raw in enumerate(result.get("claims") or [], start=1):
        if not isinstance(raw, Mapping):
            continue
        kind = str(raw.get("kind") or "claim")
        text = str(raw.get("text") or "")
        confidence = str(raw.get("confidence") or "")
        with st.expander(f"{index}. {kind} · {text}"):
            st.caption(f"jistota: {confidence}")
            evidence = raw.get("evidence")
            if isinstance(evidence, Mapping):
                _render_reconciliation(evidence, conversation, db_path)
            else:
                st.error("Claim nemá materializovanou evidence.")


def _interpretation_tab(
    filtered: pd.DataFrame,
    conversation: pd.DataFrame,
    *,
    db_path: str | None,
) -> None:
    st.caption(
        "Runtime v2: program připraví malý evidence pack; model vidí pouze E-label, odesílatele, čas a text. "
        "Canonical IDs a source provenance zůstávají lokálně a připojí se až po inference."
    )
    _manual_picker(filtered)

    selected_ids = [str(value) for value in st.session_state.get("runtime_selected_ids", [])]
    source = str(st.session_state.get("runtime_selection_source", "žádný"))
    st.markdown(f"**Aktivní výběr:** {source} · {len(selected_ids)} zpráv")
    if not selected_ids:
        st.info("Vyberte deterministický signál nebo ruční evidence zprávy.")
        return

    selected_frame, missing = resolve_evidence(conversation, selected_ids)
    if missing:
        st.error("Aktivní výběr obsahuje nedostupné canonical zprávy.")
        return
    with st.expander("Aktivní evidence", expanded=False):
        _message_table(selected_frame, limit=200)

    c1, c2 = st.columns(2)
    radius = int(c1.number_input("Okolní zprávy před/po evidence", 0, 20, 2, 1))
    max_chars = int(c2.number_input("Max. znaků na AI pack", 2000, 12000, 6000, 500))
    question = st.text_area("Otázka / zaměření interpretace", placeholder="Např. Jak se v tomto úseku mění způsob řešení konfliktu?").strip()

    try:
        packet = _build_packet(
            conversation,
            selected_ids,
            db_path=db_path,
            radius=radius,
        )
        packs = compile_packet_to_packs(
            packet,
            question=question or None,
            max_input_chars=max_chars,
        )
    except (ValueError, PacketProvenanceError, RuntimeValidationError) as exc:
        st.error(str(exc))
        return

    sizes = [len(json.dumps(pack.provider_payload(), ensure_ascii=False, separators=(",", ":"))) for pack in packs]
    st.info(
        f"Připraveno {len(packs)} evidence packů · největší provider vstup {max(sizes):,} znaků · "
        "source provenance se do modelu neposílá."
    )

    if not runtime_available():
        st.error("Runtime v2 není dostupný v aktuálním checkoutu.")
        return

    c1, c2, c3 = st.columns(3)
    model_name = c1.text_input("Ollama model", "qwen3:1.7b").strip()
    base_url = c2.text_input("Ollama URL", "http://localhost:11434").strip()
    timeout_seconds = float(c3.number_input("Timeout / pack (s)", 30, 900, 300, 30))

    if st.button("Ověřit lokální model"):
        try:
            status = check_local_runtime_provider(model_name=model_name, base_url=base_url)
        except RuntimeUnavailable as exc:
            st.error(str(exc))
        else:
            if status.get("status") == "ready":
                st.success(f"Model {model_name} je připraven.")
            else:
                st.error(str(status.get("error") or status.get("status")))

    if st.button("Spustit interpretaci", type="primary"):
        try:
            with st.spinner("Lokální interpretace…"):
                result = run_local_runtime(
                    packet,
                    model_name=model_name,
                    base_url=base_url,
                    user_question=question or None,
                    inference_timeout_seconds=timeout_seconds,
                    max_input_chars=max_chars,
                )
        except Exception as exc:
            st.error(f"Interpretace selhala: {exc}")
        else:
            st.session_state.runtime_last_result = result
            st.session_state.runtime_last_selection = list(selected_ids)

    last_result = st.session_state.get("runtime_last_result")
    last_selection = st.session_state.get("runtime_last_selection") or []
    if isinstance(last_result, Mapping) and list(last_selection) == selected_ids:
        _render_runtime_result(last_result, conversation, db_path)
    elif last_result:
        st.info("Poslední výsledek patří k jinému výběru zpráv.")


def main() -> None:
    install_responsive_contract(st)
    frame, info, findings, db_path = _source()
    if frame.empty:
        st.error("Zdroj neobsahuje použitelné zprávy.")
        st.stop()

    st.title("Analýza zpráv")
    st.caption(
        f"Runtime v2 · {info.label} · {len(frame):,} membership řádků · "
        f"{frame.message_id.nunique():,} canonical zpráv"
    )

    conversation_id, conversation = _conversation_selector(frame)
    filtered, start, end = _period_filter(conversation)
    conversation_findings = filter_findings(findings, [conversation_id], start=start, end=end)
    _metric_row(filtered, len(conversation_findings))

    tabs = st.tabs(["Konverzace", "Signály", "Interpretace"])
    with tabs[0]:
        st.caption("Canonical read model. AI se v této části nepoužívá.")
        _message_table(filtered)
    with tabs[1]:
        st.caption("Deterministické kandidáty z analytické vrstvy; nejsou to psychologické závěry.")
        _signal_table(conversation_findings)
        _signal_picker(conversation_findings, conversation)
    with tabs[2]:
        _interpretation_tab(filtered, conversation, db_path=db_path)


if __name__ == "__main__":
    main()
