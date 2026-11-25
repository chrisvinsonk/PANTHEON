import {
  formatExecutiveAssessment,
  formatPositionRevision,
  formatTargetedCrossExamination,
} from "./structured-agent-output";

const reportRoles = ["CEO", "CFO", "CTO", "CSO"];
const pageMargin = 18;

function printableText(value) {
  return String(value ?? "")
    .replace(/[“”]/g, '"')
    .replace(/[‘’]/g, "'")
    .replace(/[–—]/g, "-")
    .replace(/[•●]/g, "-")
    .replace(/→/g, "->")
    .replace(/\u00a0/g, " ")
    .replace(/[^\x09\x0A\x0D\x20-\xFF]/g, "");
}

function plainMarkdown(value) {
  return printableText(value)
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\(([^)]+)\)/g, "$1 ($2)")
    .replace(/`([^`]+)`/g, "$1")
    .replace(/\*\*(.*?)\*\*/g, "$1")
    .replace(/__(.*?)__/g, "$1")
    .replace(/~~(.*?)~~/g, "$1")
    .replace(/(^|[^*])\*([^*]+)\*/g, "$1$2")
    .replace(/(^|[^_])_([^_]+)_/g, "$1$2");
}

function createPdfWriter(doc) {
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const contentWidth = pageWidth - pageMargin * 2;
  const bottom = pageHeight - pageMargin;
  let cursorY = pageMargin;

  const ensureSpace = (height) => {
    if (cursorY + height > bottom) {
      doc.addPage();
      cursorY = pageMargin;
    }
  };

  const writeText = (value, {
    size = 10,
    style = "normal",
    color = [52, 52, 48],
    indent = 0,
    code = false,
  } = {}) => {
    const text = code ? printableText(value) : plainMarkdown(value);
    if (!text) return;
    doc.setFont(code ? "courier" : "helvetica", code ? "normal" : style);
    doc.setFontSize(size);
    doc.setTextColor(...color);
    const lines = doc.splitTextToSize(text, contentWidth - indent);
    const lineHeight = size * 0.43;
    for (const line of lines) {
      ensureSpace(lineHeight);
      doc.text(line, pageMargin + indent, cursorY);
      cursorY += lineHeight;
    }
  };

  const addGap = (height = 2) => {
    cursorY += height;
    ensureSpace(0);
  };

  const addSectionTitle = (title) => {
    ensureSpace(13);
    cursorY += 3;
    doc.setFont("helvetica", "bold");
    doc.setFontSize(13);
    doc.setTextColor(130, 100, 25);
    doc.text(printableText(title), pageMargin, cursorY);
    cursorY += 6;
    doc.setDrawColor(212, 175, 55);
    doc.setLineWidth(0.25);
    doc.line(pageMargin, cursorY, pageWidth - pageMargin, cursorY);
    cursorY += 4;
  };

  const addMarkdown = (markdown) => {
    const source = printableText(markdown);
    let inCodeBlock = false;
    let paragraph = [];

    const flushParagraph = () => {
      if (!paragraph.length) return;
      writeText(paragraph.join(" "));
      paragraph = [];
      addGap(1.5);
    };

    for (const line of source.split(/\r?\n/)) {
      if (/^\s*```/.test(line)) {
        flushParagraph();
        inCodeBlock = !inCodeBlock;
        addGap(1);
        continue;
      }
      if (inCodeBlock) {
        writeText(line || " ", { size: 9, indent: 4, code: true });
        continue;
      }
      if (!line.trim()) {
        flushParagraph();
        continue;
      }

      const heading = line.match(/^\s*(#{1,6})\s+(.+?)\s*#*\s*$/);
      if (heading) {
        flushParagraph();
        const size = Math.max(10, 16 - heading[1].length);
        writeText(heading[2], {
          size,
          style: "bold",
          color: [35, 35, 31],
        });
        addGap(1);
        continue;
      }

      const listItem = line.match(/^\s*(?:[-+*]|\d+[.)])\s+(.+)$/);
      if (listItem) {
        flushParagraph();
        writeText(`- ${listItem[1]}`, { indent: 4 });
        continue;
      }

      const quote = line.match(/^\s*>\s?(.*)$/);
      if (quote) {
        flushParagraph();
        writeText(quote[1], { indent: 6, color: [92, 92, 84] });
        continue;
      }

      if (/^\s*\|?\s*:?-{3,}/.test(line) && line.includes("|")) continue;
      if (line.includes("|") && /^\s*\|?.+\|.+\|?\s*$/.test(line)) {
        flushParagraph();
        writeText(
          line.split("|").map((cell) => cell.trim()).filter(Boolean).join("  |  "),
          { size: 9 },
        );
        continue;
      }

      paragraph.push(line.trim());
    }
    flushParagraph();
  };

  return {
    addGap,
    addMarkdown,
    addSectionTitle,
    addText: writeText,
    pageHeight,
    pageWidth,
  };
}

function addReportSection(writer, title, content) {
  if (!content?.trim()) return;
  writer.addSectionTitle(title);
  writer.addMarkdown(content);
}

export async function createBoardMeetingReportPdf(meeting, evidenceRegister = []) {
  const { jsPDF } = await import("jspdf");
  const doc = new jsPDF({ format: "a4", unit: "mm" });
  const writer = createPdfWriter(doc);
  const resolution = meeting.resolution || {};
  const decisionStatus = resolution.decision_status || meeting.status || "draft";
  const createdAt = meeting.created_at
    ? new Date(meeting.created_at).toLocaleString()
    : "Not recorded";

  doc.setProperties({
    title: `Board Meeting Report - ${meeting.title}`,
    subject: "The Pantheon board meeting report",
    creator: "The Pantheon",
  });
  writer.addText("THE PANTHEON", {
    size: 10,
    style: "bold",
    color: [130, 100, 25],
  });
  writer.addText("BOARD MEETING REPORT", {
    size: 9,
    color: [112, 112, 104],
  });
  writer.addGap(3);
  writer.addText(meeting.title || "Untitled council meeting", {
    size: 20,
    style: "bold",
    color: [35, 35, 31],
  });
  writer.addText(`Record #${meeting.id}  |  ${createdAt}  |  ${decisionStatus.replaceAll("_", " ")}`, {
    size: 9,
    color: [92, 92, 84],
  });
  writer.addGap(4);
  writer.addSectionTitle("Meeting brief");
  writer.addText("Agenda", { size: 10, style: "bold", color: [35, 35, 31] });
  writer.addMarkdown(meeting.agenda || "No agenda recorded.");
  if (meeting.founder_context?.trim()) {
    writer.addGap(2);
    writer.addText("Founder context", { size: 10, style: "bold", color: [35, 35, 31] });
    writer.addMarkdown(meeting.founder_context);
  }

  if (evidenceRegister.length) {
    writer.addSectionTitle("Evidence Register snapshot");
    for (const item of evidenceRegister) {
      writer.addText(`EVIDENCE-${item.id} · ${item.category} · ${item.classification} · ${item.source_provider || "manual"} · quality ${item.evidence_quality}`, {
        size: 9,
        style: "bold",
        color: [35, 35, 31],
      });
      writer.addMarkdown(item.claim);
      if (item.source_title || item.source_reference || item.source_url) {
        writer.addText(
          [item.source_title, item.source_reference, item.source_url]
            .filter(Boolean)
            .join(" | "),
          { size: 8, color: [92, 92, 84] },
        );
      }
      writer.addText(
        `Publication: ${item.publication_date || "unknown"} | Retrieved: ${
          item.retrieved_at ? new Date(item.retrieved_at).toLocaleDateString() : "not recorded"
        }`,
        { size: 8, color: [112, 112, 104] },
      );
      writer.addText(
        `Relied on by: ${(item.relying_executives || []).join(", ") || "none recorded"} | `
        + `Challenged: ${item.challenged ? (item.challenged_by || []).join(", ") || "yes" : "no"} | `
        + `Disputed: ${item.disputed ? (item.disputed_by || []).join(", ") || "yes" : "no"}`,
        { size: 8, color: [112, 112, 104] },
      );
      if (item.limitations?.trim()) writer.addMarkdown(`Limitations: ${item.limitations}`);
      if (item.dispute_notes?.trim()) writer.addMarkdown(`Dispute notes: ${item.dispute_notes}`);
      writer.addGap(2);
    }
  }

  addReportSection(writer, "Pantheon synthesis", resolution.recommendation);
  addReportSection(writer, "Rationale", resolution.rationale);
  addReportSection(writer, "Dissent and open questions", resolution.dissent_and_open_questions);

  for (const [phase, title, field] of [
    ["assessment", "Independent executive assessments", "assessment"],
    ["challenge", "Executive challenge round", "critique"],
  ]) {
    const contributions = meeting.contributions || [];
    const hasResponses = reportRoles.some((role) =>
      contributions.some((item) => item.role === role && item.phase === phase && item[field]?.trim()),
    );
    if (!hasResponses) continue;

    writer.addSectionTitle(title);
    for (const role of reportRoles) {
      const contribution = contributions.find((item) => item.role === role && item.phase === phase);
      if (!contribution?.[field]?.trim()) continue;
      writer.addText(role, { size: 11, style: "bold", color: [35, 35, 31] });
      if (contribution.model_name) {
        writer.addText(
          `${contribution.model_provider || "Provider unknown"} / ${contribution.model_name}`,
          { size: 8, color: [112, 112, 104] },
        );
      }
      writer.addMarkdown(
        phase === "assessment"
          ? formatExecutiveAssessment(contribution[field])
          : formatTargetedCrossExamination(contribution[field], meeting.contributions),
      );
      writer.addGap(2);
    }
  }

  const contributions = meeting.contributions || [];
  const hasRevisions = reportRoles.some((role) =>
    contributions.some((item) => item.role === role && item.revision?.trim()),
  );
  if (hasRevisions) {
    writer.addSectionTitle("Executive position revisions");
    for (const role of reportRoles) {
      const contribution = contributions.find((item) => item.role === role && item.revision?.trim());
      if (!contribution) continue;
      writer.addText(role, { size: 11, style: "bold", color: [35, 35, 31] });
      writer.addMarkdown(formatPositionRevision(contribution.revision));
      writer.addGap(2);
    }
  }

  if (resolution.decision_status || resolution.founder_notes?.trim()) {
    writer.addSectionTitle("Founder decree");
    writer.addText(`Decision status: ${decisionStatus.replaceAll("_", " ")}`, {
      size: 10,
      style: "bold",
      color: [35, 35, 31],
    });
    if (resolution.founder_notes?.trim()) writer.addMarkdown(resolution.founder_notes);
  }

  const pageCount = doc.getNumberOfPages();
  for (let page = 1; page <= pageCount; page += 1) {
    doc.setPage(page);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(8);
    doc.setTextColor(125, 125, 116);
    doc.text(
      `THE PANTHEON  |  BOARD REPORT  |  ${page} / ${pageCount}`,
      writer.pageWidth - pageMargin,
      writer.pageHeight - 8,
      { align: "right" },
    );
  }

  return doc.output("blob");
}

function reportFilename(meeting) {
  const slug = (meeting.title || "meeting")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 60);
  return `pantheon-board-report-${meeting.id}-${slug || "meeting"}.pdf`;
}

export async function downloadBoardMeetingReport(meeting, evidenceRegister = []) {
  const report = await createBoardMeetingReportPdf(meeting, evidenceRegister);
  const downloadUrl = URL.createObjectURL(report);
  const link = document.createElement("a");
  link.href = downloadUrl;
  link.download = reportFilename(meeting);
  link.style.display = "none";
  document.body.appendChild(link);
  try {
    link.click();
  } finally {
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
  }
}
