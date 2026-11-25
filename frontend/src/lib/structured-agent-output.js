function parseStructured(content) {
  const source = String(content ?? "").trim();
  const fenced = source.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  try {
    return JSON.parse(fenced ? fenced[1] : source);
  } catch {
    return null;
  }
}

function claimSection(title, claims) {
  const items = Array.isArray(claims)
    ? claims.map((item) => `- **${item.classification || "unclassified"}:** ${item.claim || ""}`
      + (item.source_evidence_ids?.length
        ? ` *(Evidence: ${item.source_evidence_ids.map((id) => `EVIDENCE-${id}`).join(", ")})*`
        : ""))
    : [];
  return `### ${title}\n${items.length ? items.join("\n") : "- None stated."}`;
}

export function formatExecutiveAssessment(content) {
  const assessment = parseStructured(content);
  if (assessment?.schema_version !== 1 || !assessment.executive_position) {
    return content || "";
  }
  return [
    `## Position: ${assessment.executive_position}`,
    `**Recommendation:** ${assessment.recommendation || "Not provided."}`,
    `**Confidence:** ${assessment.confidence || "Not provided."}`,
    ...(assessment.decision_gates === undefined
      ? ["**Compatibility note:** This saved assessment predates decision gates; none are inferred."]
      : []),
    ...[
      ["Supporting facts", "supporting_facts"],
      ["Assumptions", "assumptions"],
      ["Hypotheses", "hypotheses"],
      ["Unknowns", "unknowns"],
      ["Risks", "risks"],
      ["Alternatives", "alternatives"],
      ["Dependencies", "dependencies"],
      ["Success criteria", "success_criteria"],
      ["Decision gates", "decision_gates"],
    ].map(([title, field]) => claimSection(title, assessment[field])),
  ].join("\n\n");
}

export function formatPositionExtraction(content) {
  const extraction = parseStructured(content);
  if (extraction?.schema_version !== 1 || !Array.isArray(extraction.executives)) {
    return content || "No position extraction was recorded for this meeting.";
  }
  const disagreementSections = [
    ["Position-label divergences", extraction.position_label_divergences],
    ["Recommendation variations", extraction.recommendation_divergences],
    ["Evidence-classification differences", extraction.claim_classification_divergences],
  ].map(([title, items]) =>
    `### ${title}\n${Array.isArray(items) && items.length
      ? items.map((item) => `- ${item}`).join("\n")
      : "- None detected; this is not evidence of agreement."}`,
  );
  const executiveSections = extraction.executives.map((executive) => {
    if (!executive.is_structured) {
      return `### ${executive.role} · legacy assessment\n`
        + "This assessment was not schema-validated; no structured position or claims were inferred.";
    }
    const statements = Array.isArray(executive.statements)
      ? executive.statements.map((item) =>
        `- \`${item.claim_id}\`${item.classification ? ` [${item.classification}]` : ""}: ${item.statement}`
        + (item.source_evidence_ids?.length
          ? ` *(Evidence: ${item.source_evidence_ids.map((id) => `EVIDENCE-${id}`).join(", ")})*`
          : ""),
      )
      : [];
    return [
      `### ${executive.role} · ${executive.executive_position}`,
      `**Recommendation:** ${executive.recommendation || "Not provided."}`,
      `**Confidence:** ${executive.confidence || "Not provided."}`,
      ...(executive.compatibility_missing_fields?.length
        ? [`**Compatibility note:** No missing fields were inferred: ${executive.compatibility_missing_fields.join(", ")}.`]
        : []),
      "#### Extracted claims",
      statements.length ? statements.join("\n") : "- None stated.",
    ].join("\n\n");
  });
  return [
    "# Deterministic position extraction",
    "Claim IDs point to the source assessment; extracted differences are candidates, not an automatic consensus or final judgment.",
    ...disagreementSections,
    ...executiveSections,
  ].join("\n\n");
}

export function formatTargetedCrossExamination(content, assessmentSources = []) {
  const examination = parseStructured(content);
  if (examination?.schema_version !== 1 || !Array.isArray(examination.challenges)) {
    return content || "No targeted cross-examination was recorded for this meeting.";
  }
  const assessmentFor = (role) => assessmentSources.find(
    (item) => item.role === role && (item.phase === "assessment" || item.assessment),
  );
  const statementFor = (challenge) => {
    const source = assessmentFor(challenge.target_role);
    const assessment = parseStructured(source?.content || source?.assessment);
    const claimId = String(challenge.target_claim_id || "");
    const rolePrefix = `${challenge.target_role}.`;
    if (!claimId.startsWith(rolePrefix)) return null;
    const path = claimId.slice(rolePrefix.length).split(".");
    if (path[0] === "executive_position") return assessment?.executive_position;
    if (path[0] === "recommendation") return assessment?.recommendation;
    if (path[0] === "legacy_assessment") {
      return source?.content || source?.assessment || null;
    }
    const index = Number(path[1]) - 1;
    if (path.length !== 2 || !Number.isInteger(index) || index < 0) return null;
    return assessment?.[path[0]]?.[index]?.claim || null;
  };
  return [
    "## Targeted cross-examination",
    ...examination.challenges.map((challenge) => {
      const statement = statementFor(challenge);
      return `### ${challenge.target_role || "Executive"} · \`${challenge.target_claim_id || "claim"}\`\n`
        + (statement ? `**Claim:** ${statement}\n\n` : "")
        + `**Challenge:** ${challenge.challenge_question || "Not provided."}\n\n`
        + `**Why it matters:** ${challenge.why_it_matters || "Not provided."}\n\n`
        + `**Evidence considered:** ${(challenge.source_evidence_ids || []).map((id) => `EVIDENCE-${id}`).join(", ") || "None"}\n\n`
        + `**Evidence disputed:** ${(challenge.disputed_evidence_ids || []).map((id) => `EVIDENCE-${id}`).join(", ") || "None"}`;
    }),
  ].join("\n\n");
}

export function formatPositionRevision(content) {
  const revision = parseStructured(content);
  if (revision?.schema_version !== 1 || !revision.position_change) {
    return content || "No position revision was recorded for this meeting.";
  }
  return [
    `## Position change: ${revision.position_change}`,
    `**Previous position:** ${revision.previous_position || "Not stated."}`,
    `**Revised position:** ${revision.revised_position || "Withdrawn."}`,
    `**Reason:** ${revision.reason_for_change || "Not provided."}`,
    claimSection("Arguments that changed my view", revision.arguments_that_changed_my_view),
    claimSection("Remaining disagreements", revision.remaining_disagreements),
  ].join("\n\n");
}

export function formatBoardSynthesis(content) {
  const synthesis = parseStructured(content);
  if (synthesis?.schema_version !== 1 || !synthesis.recommendation) {
    return content || "";
  }
  const listSection = (title, items) =>
    `## ${title}\n${Array.isArray(items) && items.length
      ? items.map((item) => `- ${item}`).join("\n")
      : "- None identified."}`;
  const evidence = Array.isArray(synthesis.evidence_register)
    ? synthesis.evidence_register.map(
    (item) => `- **${item.classification || "unclassified"} · ${item.source_role || "Unknown"}:** ${item.claim || ""}`
      + (item.source_evidence_ids?.length
        ? ` *(Evidence: ${item.source_evidence_ids.map((id) => `EVIDENCE-${id}`).join(", ")})*`
        : ""),
    )
    : [];
  const actions = Array.isArray(synthesis.next_actions)
    ? synthesis.next_actions.map((item) =>
      `- **${item.action}** — Owner: ${item.owner}. `
      + `Success criteria: ${(item.success_criteria || []).join(", ") || "to be defined"}. `
      + `Decision gate: ${item.decision_gate}`,
    )
    : [];
  return [
    `# Executive summary\n${synthesis.executive_summary || ""}`,
    `## Proposed board recommendation\n${synthesis.recommendation}`,
    `## Rationale\n${synthesis.rationale || ""}`,
    listSection("Shared conclusions", synthesis.shared_conclusions),
    listSection("Genuine disagreements", synthesis.genuine_disagreements),
    listSection("Material dissent", synthesis.material_dissent),
    `## Evidence classification\n${evidence.length ? evidence.join("\n") : "- No claims classified."}`,
    listSection("Unresolved questions", synthesis.unresolved_questions),
    `## Recommended next actions\n${actions.length ? actions.join("\n") : "- None proposed."}`,
    listSection("Decision gates", synthesis.decision_gates),
    "**Founder authority:** This is a recommendation, not an approval. The founder records the decision.",
  ].join("\n\n");
}
