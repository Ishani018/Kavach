// build_deck.js
// Kavach v2 Progress Review — PptxGenJS deck builder
//
// Carries forward the "Blue Minimalist" palette from the April capstone deck
// (Kavach_Deck_v5_final.html) so the team and advisor immediately see
// continuity. Visual motif: thin navy accent at top of each content slide,
// section number bottom-right, all content on a soft light-blue background.

const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");

const {
  FaShieldAlt, FaExclamationTriangle, FaCheckCircle, FaCogs, FaCode,
  FaKey, FaPaperPlane, FaCompass, FaBalanceScale, FaUserShield,
  FaTerminal, FaFileAlt, FaBookOpen, FaFlask, FaChartLine,
  FaClipboardCheck, FaProjectDiagram, FaUsers, FaLightbulb,
  FaArrowRight, FaArrowDown, FaTimes, FaCheck, FaSearchLocation,
  FaServer, FaPlug, FaDatabase, FaGavel, FaQuestionCircle,
  FaBug, FaWrench, FaListAlt, FaRocket, FaTrophy, FaRegFile,
} = require("react-icons/fa");

// ──────────────────────────────────────────────────────────────────────
// Color palette — pulled from Kavach_Deck_v5_final.html for continuity
// ──────────────────────────────────────────────────────────────────────
const C = {
  navy:        "0B1C3A",
  navyDeep:    "081530",
  blue:        "3B7EE5",
  blueDeep:    "1E4FA8",
  blueLite:    "7FB0FF",
  bgLite:      "ECF1F9",
  bgWhite:     "FFFFFF",
  textDark:    "0B1C3A",
  textMuted:   "5A6B85",
  textOnDark:  "ECF1F9",
  alert:       "E63946",
  teal:        "2A9D8F",   // "new" items
  gold:        "E9C46A",   // emphasis
  goldDeep:    "B8962C",
  border:      "C9D6EC",
};

// ──────────────────────────────────────────────────────────────────────
// Icon helper — rasterize react-icons to base64 PNG
// ──────────────────────────────────────────────────────────────────────
async function ico(IconComp, color = C.navy, size = 256) {
  const svg = ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComp, { color: "#" + color, size: String(size) })
  );
  const png = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + png.toString("base64");
}

// ──────────────────────────────────────────────────────────────────────
// Slide chrome — applied to every content slide for visual consistency
// ──────────────────────────────────────────────────────────────────────
function chrome(slide, slideNum, totalSlides, sectionLabel = "") {
  // Soft background
  slide.background = { color: C.bgLite };

  // Thin top accent line (the visual motif of this deck)
  slide.addShape("rect", {
    x: 0, y: 0, w: 13.333, h: 0.08,
    fill: { color: C.blue }, line: { color: C.blue, width: 0 },
  });

  // Bottom-right slide marker — matches the April deck's "01 / 13" style
  slide.addText(
    [
      { text: "Kavach · कवच", options: { color: C.textMuted, fontSize: 9 } },
      { text: "    " + String(slideNum).padStart(2, "0") + " / " + totalSlides,
        options: { color: C.textMuted, fontSize: 9, bold: true } },
    ],
    { x: 9.0, y: 7.05, w: 4.0, h: 0.3, align: "right", margin: 0, fontFace: "Calibri" }
  );

  // Section label top-left (small, muted)
  if (sectionLabel) {
    slide.addText(sectionLabel, {
      x: 0.5, y: 0.18, w: 8, h: 0.3,
      fontSize: 10, color: C.textMuted, fontFace: "Calibri",
      bold: true, charSpacing: 4, margin: 0,
    });
  }
}

// ──────────────────────────────────────────────────────────────────────
// Main
// ──────────────────────────────────────────────────────────────────────
async function build() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE";       // 13.3" × 7.5"
  pres.title  = "Kavach v2 — Progress Review";
  pres.author = "Kavach Team, PES University";
  pres.company = "PES University · Capstone PW26_RB_03";

  const TOTAL = 20;

  // Pre-render all icons we'll need
  const ICONS = {
    shield:    await ico(FaShieldAlt,         C.bgLite,  256),
    shieldNavy:await ico(FaShieldAlt,         C.navy,    256),
    warn:      await ico(FaExclamationTriangle, C.alert, 256),
    warnGold:  await ico(FaExclamationTriangle, C.goldDeep, 256),
    check:     await ico(FaCheckCircle,       C.teal,    256),
    cog:       await ico(FaCogs,              C.blueDeep,256),
    code:      await ico(FaCode,              C.blueDeep,256),
    key:       await ico(FaKey,               C.blueDeep,256),
    plane:     await ico(FaPaperPlane,        C.blueDeep,256),
    compass:   await ico(FaCompass,           C.blueDeep,256),
    scale:     await ico(FaBalanceScale,      C.blueDeep,256),
    userShield:await ico(FaUserShield,        C.blueDeep,256),
    terminal:  await ico(FaTerminal,          C.blueDeep,256),
    file:      await ico(FaFileAlt,           C.blueDeep,256),
    book:      await ico(FaBookOpen,          C.blueDeep,256),
    flask:     await ico(FaFlask,             C.blueDeep,256),
    chart:     await ico(FaChartLine,         C.blueDeep,256),
    clipboard: await ico(FaClipboardCheck,    C.teal,    256),
    diagram:   await ico(FaProjectDiagram,    C.blueDeep,256),
    users:     await ico(FaUsers,             C.blueDeep,256),
    bulb:      await ico(FaLightbulb,         C.goldDeep,256),
    arrowR:    await ico(FaArrowRight,        C.blueDeep,256),
    arrowD:    await ico(FaArrowDown,         C.textMuted,256),
    x:         await ico(FaTimes,             C.alert,   256),
    chk:       await ico(FaCheck,             C.teal,    256),
    locate:    await ico(FaSearchLocation,    C.blueDeep,256),
    server:    await ico(FaServer,            C.blueDeep,256),
    plug:      await ico(FaPlug,              C.blueDeep,256),
    db:        await ico(FaDatabase,          C.blueDeep,256),
    gavel:     await ico(FaGavel,             C.blueDeep,256),
    question:  await ico(FaQuestionCircle,    C.blueDeep,256),
    bug:       await ico(FaBug,               C.alert,   256),
    wrench:    await ico(FaWrench,            C.teal,    256),
    list:      await ico(FaListAlt,           C.blueDeep,256),
    rocket:    await ico(FaRocket,            C.teal,    256),
    trophy:    await ico(FaTrophy,            C.goldDeep,256),
    fileLite:  await ico(FaRegFile,           C.blueDeep,256),
  };

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 1 — Title
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.navy };

    // Top accent strip
    s.addShape("rect", {
      x: 0, y: 0, w: 13.333, h: 0.12,
      fill: { color: C.blue }, line: { width: 0 },
    });

    // Big watermark कवच (Sanskrit) in the background, very low contrast
    s.addText("कवच", {
      x: 6.5, y: 0.4, w: 6.5, h: 4.5,
      fontSize: 350, color: C.blueDeep, transparency: 70,
      fontFace: "Georgia", align: "center", valign: "middle", margin: 0,
    });

    // Top label
    s.addText("CAPSTONE PROGRESS REVIEW    ·    MAY 2026", {
      x: 0.7, y: 0.6, w: 12, h: 0.4,
      fontSize: 11, color: C.blueLite, bold: true, charSpacing: 6,
      fontFace: "Calibri", margin: 0,
    });

    // Project subtitle
    s.addText("Kavach", {
      x: 0.7, y: 1.4, w: 12, h: 1.5,
      fontSize: 96, color: C.bgLite, bold: true,
      fontFace: "Georgia", margin: 0,
    });

    s.addText("From a post-hoc monitor to a real-time semantic firewall", {
      x: 0.7, y: 2.9, w: 12, h: 0.6,
      fontSize: 22, color: C.blueLite, fontFace: "Calibri",
      italic: true, margin: 0,
    });

    // Subtitle accent line
    s.addShape("rect", {
      x: 0.7, y: 3.7, w: 1.0, h: 0.04,
      fill: { color: C.blue }, line: { width: 0 },
    });

    // Status pill
    s.addShape("roundRect", {
      x: 0.7, y: 4.0, w: 5.5, h: 0.55,
      fill: { color: C.blueDeep }, line: { color: C.blue, width: 1 },
      rectRadius: 0.08,
    });
    s.addText("PHASE 2  ·  PARLIAMENT-OF-MINISTERS", {
      x: 0.7, y: 4.0, w: 5.5, h: 0.55,
      fontSize: 13, color: C.bgLite, bold: true,
      align: "center", valign: "middle", charSpacing: 4,
      fontFace: "Calibri", margin: 0,
    });

    // Team + advisor block — bottom
    s.addText("PES UNIVERSITY  ·  CAPSTONE PW26_RB_03", {
      x: 0.7, y: 5.6, w: 12, h: 0.3,
      fontSize: 10, color: C.blueLite, bold: true, charSpacing: 4,
      fontFace: "Calibri", margin: 0,
    });
    s.addText(
      [
        { text: "Team   ", options: { color: C.blueLite, fontSize: 12, bold: true } },
        { text: "Jamieboy · Janya Mahesh · Pranitha Goduguluri · Parv Parmar · Ishani Chakraborty",
          options: { color: C.bgLite, fontSize: 13 } },
      ],
      { x: 0.7, y: 5.95, w: 12, h: 0.4, fontFace: "Calibri", margin: 0 }
    );
    s.addText(
      [
        { text: "Guide   ", options: { color: C.blueLite, fontSize: 12, bold: true } },
        { text: "Prof. Rajesh Banginwar     ", options: { color: C.bgLite, fontSize: 13 } },
        { text: "·   Hardware   ", options: { color: C.blueLite, fontSize: 12, bold: true } },
        { text: "Dell Precision 3660 · i9-13900 · 128 GB · RTX 4090",
          options: { color: C.bgLite, fontSize: 13 } },
      ],
      { x: 0.7, y: 6.4, w: 12, h: 0.4, fontFace: "Calibri", margin: 0 }
    );
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 2 — Executive summary
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 2, TOTAL, "01  ·  EXECUTIVE SUMMARY");

    s.addText("Where we are, in three sentences", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });

    // Three large statement cards
    const cards = [
      {
        num: "01",
        title: "April was a monitor.",
        body: "We shipped 10 regex rules, an SQLite ledger, and a working ClawHavoc demo. Catch attacks after they fire — useful for forensics, not for prevention.",
        accent: C.alert,
      },
      {
        num: "02",
        title: "May is a parliament.",
        body: "Four embedding-based ministers (EXECUTOR · VAULT · CHANNEL · NAVIGATOR), a COMPASS alignment oracle, a deterministic speaker, and a 200-pattern v2 corpus written from MITRE ATT&CK rather than from a known attack.",
        accent: C.teal,
      },
      {
        num: "03",
        title: "June is real-time enforcement.",
        body: "OpenClaw PR-1 fixes the two upstream bugs that prevent before_tool_call from firing. With those landed, every tool call routes through the parliament before execution.",
        accent: C.gold,
      },
    ];

    cards.forEach((c, i) => {
      const cardX = 0.5;
      const cardY = 1.55 + i * 1.7;
      const cardW = 12.3;
      const cardH = 1.5;

      // Card background
      s.addShape("rect", {
        x: cardX, y: cardY, w: cardW, h: cardH,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 },
      });
      // Left accent bar
      s.addShape("rect", {
        x: cardX, y: cardY, w: 0.12, h: cardH,
        fill: { color: c.accent }, line: { width: 0 },
      });
      // Big number
      s.addText(c.num, {
        x: cardX + 0.4, y: cardY + 0.15, w: 1.2, h: 1.2,
        fontSize: 60, color: c.accent, bold: true, fontFace: "Georgia",
        valign: "middle", margin: 0,
      });
      // Title
      s.addText(c.title, {
        x: cardX + 1.7, y: cardY + 0.2, w: cardW - 2.0, h: 0.5,
        fontSize: 22, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
      });
      // Body
      s.addText(c.body, {
        x: cardX + 1.7, y: cardY + 0.7, w: cardW - 2.0, h: 0.7,
        fontSize: 13, color: C.textDark, fontFace: "Calibri", margin: 0,
      });
    });

    // Bottom strap line
    s.addText(
      "The single most important thing right now: fix the OpenClaw bugs so before_tool_call actually fires. Everything else is downstream.",
      { x: 0.5, y: 6.85, w: 12.3, h: 0.4,
        fontSize: 12, color: C.textMuted, italic: true, align: "center",
        fontFace: "Calibri", margin: 0,
      }
    );
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 3 — Recap: what April shipped
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 3, TOTAL, "02  ·  RECAP — APRIL BASELINE");

    s.addText("What the April demo showed", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });
    s.addText("The blue deck delivered Phase 1 — a post-hoc detection monitor backed by 10 CVE-mapped regex rules.", {
      x: 0.5, y: 1.3, w: 12.3, h: 0.4,
      fontSize: 14, color: C.textMuted, italic: true, fontFace: "Calibri", margin: 0,
    });

    // Two-column layout: left = what we built (positive), right = what was missing (limitation)
    const cards = [
      {
        x: 0.5, w: 6.0, head: "WHAT SHIPPED", accent: C.teal, icon: ICONS.check,
        rows: [
          ["10 regex rules", "Each mapped to a CVE or CWE: external fetch, pipe-to-shell, SSH key access, persistence, secrets, sandbox-disabled."],
          ["SQLite audit ledger", "Every detection logged with session, turn, verdict, matched rule, CVE."],
          ["Stateful retry detection", "A flag-changed retry of a previously blocked call is recognized."],
          ["ClawHavoc demo", "End-to-end playback of CVE-2026-25253: a curl-pipe-bash hidden in a skill's prerequisites."],
          ["~500 lines of Python", "Tails session.jsonl that OpenClaw already writes — no patches, no wrappers."],
        ],
      },
      {
        x: 6.85, w: 6.0, head: "WHAT WAS HONESTLY MISSING", accent: C.alert, icon: ICONS.x,
        rows: [
          ["No real-time interception", "Detection happens after the tool already executed. This is a forensics tool, not a guardrail."],
          ["No semantic generalization", "Regex on tool names. Does not catch a novel command achieving the same intent."],
          ["No benchmark numbers", "Zero recall, precision, FPR, or latency measurements."],
          ["No proof of corpus generalization", "Rules were written staring at known attacks — sophisticated keyword matching, not understanding."],
          ["Upstream RFCs were redundant", "We proposed before_delivery; the OpenClaw SDK already has message_sending. The real bug is elsewhere."],
        ],
      },
    ];

    cards.forEach(c => {
      // Card frame
      s.addShape("rect", {
        x: c.x, y: 1.85, w: c.w, h: 5.0,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 },
      });
      // Header bar
      s.addShape("rect", {
        x: c.x, y: 1.85, w: c.w, h: 0.5,
        fill: { color: c.accent }, line: { width: 0 },
      });
      s.addImage({ data: c.icon, x: c.x + 0.2, y: 1.95, w: 0.3, h: 0.3 });
      s.addText(c.head, {
        x: c.x + 0.6, y: 1.85, w: c.w - 0.6, h: 0.5,
        fontSize: 13, color: C.bgLite, bold: true, charSpacing: 4,
        valign: "middle", fontFace: "Calibri", margin: 0,
      });
      // Rows
      c.rows.forEach((row, i) => {
        const rowY = 2.55 + i * 0.85;
        s.addText(row[0], {
          x: c.x + 0.25, y: rowY, w: c.w - 0.4, h: 0.3,
          fontSize: 14, color: C.navy, bold: true, fontFace: "Calibri", margin: 0,
        });
        s.addText(row[1], {
          x: c.x + 0.25, y: rowY + 0.32, w: c.w - 0.4, h: 0.5,
          fontSize: 11, color: C.textMuted, fontFace: "Calibri", margin: 0,
        });
      });
    });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 4 — The honest reckoning
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 4, TOTAL, "03  ·  THE HONEST RECKONING");

    s.addText("The decision we made between April and May", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });
    s.addText("If we ship a benchmark of regex rules tested on the attacks the regex was written for, we will be cited against the project at review time. So we stopped, listed what was actually wrong, and rebuilt.", {
      x: 0.5, y: 1.35, w: 12.3, h: 0.7,
      fontSize: 14, color: C.textMuted, italic: true, fontFace: "Calibri", margin: 0,
    });

    // Three diagnosis blocks
    const blocks = [
      {
        x: 0.5,  title: "DIAGNOSIS",   accent: C.alert,
        head: "What was wrong", icon: ICONS.bug,
        items: [
          "Detection ran after execution. CVE-class harm was already done.",
          "The corpus was authored while looking at known attacks — sophisticated keyword matching.",
          "The proposed RFC duplicated an SDK feature. Wrong target.",
          "No FPR measurement. Could not distinguish a tight detector from a trigger-happy one.",
        ],
      },
      {
        x: 4.7,  title: "DECISION",    accent: C.gold,
        head: "What we changed", icon: ICONS.bulb,
        items: [
          "Move enforcement from after-tool to before-tool. Real interception or nothing.",
          "Rewrite the corpus from MITRE ATT&CK and OWASP Agentic — never from a CVE we've seen.",
          "Drop the new-RFC plan; fix the two existing OpenClaw bugs that block before_tool_call.",
          "Add a benign-trace gate: FPR < 5% before any attack benchmark runs.",
        ],
      },
      {
        x: 8.9,  title: "DELIVERY",    accent: C.teal,
        head: "What this slide deck shows", icon: ICONS.wrench,
        items: [
          "Parliament service with five collections and a deterministic speaker.",
          "200 v2 patterns; merge validates with zero protocol violations.",
          "PR-1 patch spec for OpenClaw bugs #5513 and #5943, with vitest regressions.",
          "Reproducibility checklist that orders the validation gates correctly.",
        ],
      },
    ];

    blocks.forEach(b => {
      // Card
      s.addShape("rect", {
        x: b.x, y: 2.25, w: 4.0, h: 4.6,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 },
      });
      // Top accent
      s.addShape("rect", {
        x: b.x, y: 2.25, w: 4.0, h: 0.08,
        fill: { color: b.accent }, line: { width: 0 },
      });
      // Title pip
      s.addText(b.title, {
        x: b.x + 0.25, y: 2.45, w: 3.5, h: 0.3,
        fontSize: 10, color: b.accent, bold: true, charSpacing: 4,
        fontFace: "Calibri", margin: 0,
      });
      // Icon
      s.addImage({ data: b.icon, x: b.x + 0.25, y: 2.85, w: 0.4, h: 0.4 });
      // Head
      s.addText(b.head, {
        x: b.x + 0.8, y: 2.83, w: 3.0, h: 0.5,
        fontSize: 18, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
      });
      // Items
      const itemRuns = [];
      b.items.forEach((it, i) => {
        itemRuns.push({ text: it, options: { bullet: true, breakLine: i < b.items.length - 1, paraSpaceAfter: 8 } });
      });
      s.addText(itemRuns, {
        x: b.x + 0.25, y: 3.45, w: 3.6, h: 3.3,
        fontSize: 11, color: C.textDark, fontFace: "Calibri", margin: 0,
        valign: "top",
      });
    });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 5 — The bottleneck (OpenClaw bugs)
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 5, TOTAL, "04  ·  THE CRITICAL-PATH FIX");

    s.addText("Two upstream OpenClaw bugs are blocking everything", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });
    s.addText("Until before_tool_call actually fires, no security plugin (Kavach included) can be a real guardrail. PR-1 ships both fixes with vitest regressions.", {
      x: 0.5, y: 1.35, w: 12.3, h: 0.7,
      fontSize: 14, color: C.textMuted, italic: true, fontFace: "Calibri", margin: 0,
    });

    // Two big bug cards
    const bugs = [
      {
        x: 0.5, num: "#5513", icon: ICONS.bug,
        title: "Typed-hook runner snapshots too early",
        before: "initializeGlobalHookRunner() captures registry.typedHooks at construction time. Plugins that register their hooks during the brief register() → start() window are visible in the registry but invisible to the runner.",
        impact: "Result: the security hook is registered, looks fine on paper, and silently never fires.",
        fix:    "Replace the cached field with a getter. Read the live registry on every dispatch. Pattern already used by observability-plugin PR #6 (ISI-515).",
      },
      {
        x: 6.85, num: "#5943", icon: ICONS.bug,
        title: "before_tool_call defined but never invoked",
        before: "The hook is declared in src/plugins/hooks.ts and documented as available since v2026.3.28. But executeToolCalls() in pi-embedded-runner/run/attempt.ts (line ~254) never calls it.",
        impact: "Result: every tool runs unconditionally, regardless of any registered before_tool_call handler. The contract is unfulfilled.",
        fix:    "Wire dispatch into executeToolCalls() — sequential, deny-first. Honor block, params, and requireApproval. ~30 lines of source.",
      },
    ];

    bugs.forEach(b => {
      s.addShape("rect", {
        x: b.x, y: 2.2, w: 6.0, h: 4.7,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 },
      });
      s.addShape("rect", {
        x: b.x, y: 2.2, w: 6.0, h: 0.7,
        fill: { color: C.alert }, line: { width: 0 },
      });
      s.addImage({ data: b.icon, x: b.x + 0.2, y: 2.35, w: 0.4, h: 0.4 });
      s.addText(b.num, {
        x: b.x + 0.7, y: 2.2, w: 1.5, h: 0.7,
        fontSize: 22, color: C.bgLite, bold: true, valign: "middle",
        fontFace: "Calibri", margin: 0,
      });
      s.addText(b.title, {
        x: b.x + 2.2, y: 2.2, w: 3.7, h: 0.7,
        fontSize: 13, color: C.bgLite, valign: "middle", italic: true,
        fontFace: "Calibri", margin: 0,
      });
      // Body sections
      const sections = [
        ["THE BUG",   b.before, C.textDark],
        ["IMPACT",    b.impact, C.alert],
        ["THE FIX",   b.fix,    C.teal],
      ];
      let yy = 3.05;
      sections.forEach(sec => {
        s.addText(sec[0], {
          x: b.x + 0.25, y: yy, w: 5.5, h: 0.25,
          fontSize: 9, color: sec[2], bold: true, charSpacing: 4,
          fontFace: "Calibri", margin: 0,
        });
        s.addText(sec[1], {
          x: b.x + 0.25, y: yy + 0.25, w: 5.5, h: 1.0,
          fontSize: 11, color: C.textDark, fontFace: "Calibri", margin: 0,
        });
        yy += 1.3;
      });
    });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 6 — New architecture overview (the big diagram)
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 6, TOTAL, "05  ·  PHASE 2 ARCHITECTURE");

    s.addText("The parliament intercepts every tool call before execution", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });

    // Diagram — left to right flow
    // Layer 1: User → Agent
    // Layer 2: Plugin (with before_tool_call hook)
    // Layer 3: Parliament (COMPASS → Router → 4 ministers → Speaker)
    // Layer 4: Verdict → tool runs (or doesn't)

    // Start: User
    const drawNode = (x, y, w, h, label, sub, fill, textColor = C.textDark) => {
      s.addShape("roundRect", {
        x, y, w, h,
        fill: { color: fill }, line: { color: C.border, width: 1 },
        rectRadius: 0.06,
      });
      s.addText(label, {
        x, y: y + 0.05, w, h: h - 0.3,
        fontSize: 12, color: textColor, bold: true, align: "center",
        valign: "middle", fontFace: "Calibri", margin: 0,
      });
      s.addText(sub, {
        x, y: y + h - 0.35, w, h: 0.3,
        fontSize: 9, color: C.textMuted, align: "center",
        fontFace: "Calibri", margin: 0,
      });
    };

    const drawArrow = (x1, y1, x2, y2, color = C.blueDeep) => {
      s.addShape("line", {
        x: x1, y: y1, w: x2 - x1, h: y2 - y1,
        line: { color, width: 2, endArrowType: "triangle" },
      });
    };

    // Y baseline for top row
    const yTop = 1.7;
    const yMid = 3.2;
    const yMin = 4.7;       // ministers row
    const ySpk = 6.0;

    // User
    drawNode(0.5, yTop, 1.6, 0.7, "User", "prompt", C.bgWhite);
    drawArrow(2.1, yTop + 0.35, 2.6, yTop + 0.35);

    // Agent (OpenClaw)
    drawNode(2.6, yTop, 2.0, 0.7, "OpenClaw Agent", "Gemma 4 26B", C.bgWhite);

    // Down-arrow from agent to plugin
    drawArrow(3.6, yTop + 0.7, 3.6, yMid - 0.05, C.alert);
    s.addText("before_tool_call", {
      x: 3.7, y: yTop + 0.8, w: 1.8, h: 0.3,
      fontSize: 10, color: C.alert, italic: true, fontFace: "Calibri", margin: 0,
    });

    // Plugin
    drawNode(2.6, yMid, 2.0, 0.7, "Kavach Plugin", "TypeScript", "F0E8D8");

    // Right-arrow from plugin to parliament
    drawArrow(4.6, yMid + 0.35, 5.5, yMid + 0.35);
    s.addText("HTTP", {
      x: 4.65, y: yMid - 0.1, w: 0.85, h: 0.3,
      fontSize: 9, color: C.textMuted, italic: true, fontFace: "Calibri", margin: 0,
    });

    // Parliament container (big)
    s.addShape("roundRect", {
      x: 5.5, y: 2.45, w: 7.4, h: 4.3,
      fill: { color: C.navy }, line: { color: C.blue, width: 1 },
      rectRadius: 0.1,
    });
    s.addText("PARLIAMENT  ·  FastAPI on 127.0.0.1:8088", {
      x: 5.5, y: 2.55, w: 7.4, h: 0.3,
      fontSize: 11, color: C.blueLite, bold: true, charSpacing: 3,
      align: "center", fontFace: "Calibri", margin: 0,
    });

    // Inside parliament: COMPASS pill (top)
    s.addShape("roundRect", {
      x: 5.85, y: yMid - 0.20, w: 2.5, h: 0.55,
      fill: { color: C.gold }, line: { color: C.goldDeep, width: 1 },
      rectRadius: 0.05,
    });
    s.addText("COMPASS  →  intent ⇄ action", {
      x: 5.85, y: yMid - 0.20, w: 2.5, h: 0.55,
      fontSize: 11, color: C.navyDeep, bold: true,
      align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
    });

    // Router
    s.addShape("roundRect", {
      x: 8.5, y: yMid - 0.20, w: 2.5, h: 0.55,
      fill: { color: C.blueLite }, line: { color: C.blue, width: 1 },
      rectRadius: 0.05,
    });
    s.addText("Semantic router", {
      x: 8.5, y: yMid - 0.20, w: 2.5, h: 0.55,
      fontSize: 11, color: C.navyDeep, bold: true,
      align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
    });

    // Down-arrow from COMPASS+Router to ministers
    drawArrow(7.1, yMid + 0.4, 7.1, yMin - 0.05, C.blueLite);
    drawArrow(9.7, yMid + 0.4, 9.7, yMin - 0.05, C.blueLite);

    // Ministers row — four mini-cards
    const ministers = [
      { name: "EXECUTOR",  sub: "code-exec",  color: "C0392B" },
      { name: "VAULT",     sub: "secrets",    color: "8E44AD" },
      { name: "CHANNEL",   sub: "exfil",      color: "16A085" },
      { name: "NAVIGATOR", sub: "trajectory", color: "D68910" },
    ];
    ministers.forEach((m, i) => {
      const mx = 5.85 + i * 1.81;
      s.addShape("roundRect", {
        x: mx, y: yMin, w: 1.61, h: 0.85,
        fill: { color: C.bgLite }, line: { color: m.color, width: 1.5 },
        rectRadius: 0.05,
      });
      s.addText(m.name, {
        x: mx, y: yMin + 0.05, w: 1.61, h: 0.4,
        fontSize: 11, color: m.color, bold: true,
        align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
      });
      s.addText(m.sub, {
        x: mx, y: yMin + 0.45, w: 1.61, h: 0.35,
        fontSize: 9, color: C.textMuted,
        align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
      });
    });

    // Down-arrows from ministers to speaker
    ministers.forEach((m, i) => {
      const mx = 5.85 + i * 1.81 + 0.8;
      drawArrow(mx, yMin + 0.85, mx, ySpk - 0.05, C.blueLite);
    });

    // Speaker
    s.addShape("roundRect", {
      x: 5.85, y: ySpk, w: 7.05, h: 0.6,
      fill: { color: C.teal }, line: { color: C.teal, width: 0 },
      rectRadius: 0.05,
    });
    s.addText("SPEAKER  →  BLOCK / ESCALATE / ALLOW", {
      x: 5.85, y: ySpk, w: 7.05, h: 0.6,
      fontSize: 13, color: C.bgLite, bold: true,
      align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
    });

    // Description on the left side, bottom
    s.addText("Five separate ChromaDB collections.\nBGE-base-en-v1.5 with mean pooling and asymmetric query prefix.\nMinisters run in parallel. Speaker is deterministic — no LLM in the hot path.\nDeny-first: any single confident BLOCK suffices.", {
      x: 0.5, y: 4.7, w: 4.7, h: 2.2,
      fontSize: 11, color: C.textDark, fontFace: "Calibri",
      paraSpaceAfter: 5, margin: 0,
    });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 7 — The four ministers
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 7, TOTAL, "06  ·  MINISTERS");

    s.addText("Four specialists, disjoint corpora", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });
    s.addText("Each minister is a ChromaDB collection embedded with BGE-base. 50 patterns × 3 abstraction levels = 150 documents per collection.", {
      x: 0.5, y: 1.35, w: 12.3, h: 0.4,
      fontSize: 14, color: C.textMuted, italic: true, fontFace: "Calibri", margin: 0,
    });

    const ministers = [
      {
        name: "EXECUTOR",
        watches: "Code execution, persistence, lifecycle hooks",
        sources: "MITRE T1059, T1190, T1195, T1546, T1574  ·  OWASP Agentic A09",
        examples: "curl-pipe-bash, git-hook install, CI workflow injection, supply-chain dependency swap, kernel-module load, cron drop-in, sudoers edit",
        color: "C0392B", icon: ICONS.terminal,
      },
      {
        name: "VAULT",
        watches: "Credential and secret theft",
        sources: "MITRE T1552, T1078, T1539, T1555  ·  OWASP Agentic A02, A06",
        examples: "browser credential DB, ~/.aws/credentials, cloud metadata token, k8s service-account token, SSH agent socket, /etc/shadow, vault dump",
        color: "8E44AD", icon: ICONS.key,
      },
      {
        name: "CHANNEL",
        watches: "Data exfiltration",
        sources: "MITRE T1041, T1567, T1071, T1048, T1572  ·  OWASP Agentic A04",
        examples: "webhook paste, Discord/Slack/Telegram, anonymous S3 bucket, DNS tunnel, reverse shell, rclone sync, image-URL credential exfil",
        color: "16A085", icon: ICONS.plane,
      },
      {
        name: "NAVIGATOR",
        watches: "Trajectory drift, intent breaking, scope widening",
        sources: "MITRE T1083, T1057, T1005, T1135, T1119  ·  OWASP Agentic A01",
        examples: "scope widening, task pivot, fs/process recon, secret-pattern grep, encoding obfuscation, fake user follow-up, log clearing",
        color: "D68910", icon: ICONS.compass,
      },
    ];

    // 2x2 grid
    ministers.forEach((m, i) => {
      const col = i % 2, row = Math.floor(i / 2);
      const x = 0.5 + col * 6.35;
      const y = 1.95 + row * 2.5;
      const w = 6.0, h = 2.3;

      s.addShape("rect", {
        x, y, w, h,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 },
      });
      // Left accent
      s.addShape("rect", {
        x, y, w: 0.12, h,
        fill: { color: m.color }, line: { width: 0 },
      });
      // Title
      s.addText(m.name, {
        x: x + 0.3, y: y + 0.15, w: w - 0.6, h: 0.45,
        fontSize: 22, color: m.color, bold: true, fontFace: "Georgia", margin: 0,
      });
      // Watches subtitle
      s.addText(m.watches, {
        x: x + 0.3, y: y + 0.6, w: w - 0.6, h: 0.3,
        fontSize: 12, color: C.textDark, italic: true, fontFace: "Calibri", margin: 0,
      });
      // Sources label
      s.addText("SOURCES", {
        x: x + 0.3, y: y + 0.95, w: w - 0.6, h: 0.2,
        fontSize: 8, color: C.textMuted, bold: true, charSpacing: 3,
        fontFace: "Calibri", margin: 0,
      });
      s.addText(m.sources, {
        x: x + 0.3, y: y + 1.13, w: w - 0.6, h: 0.3,
        fontSize: 10, color: C.textDark, fontFace: "Consolas", margin: 0,
      });
      // Examples label
      s.addText("EXAMPLE PATTERNS", {
        x: x + 0.3, y: y + 1.45, w: w - 0.6, h: 0.2,
        fontSize: 8, color: C.textMuted, bold: true, charSpacing: 3,
        fontFace: "Calibri", margin: 0,
      });
      s.addText(m.examples, {
        x: x + 0.3, y: y + 1.65, w: w - 0.6, h: 0.55,
        fontSize: 10, color: C.textDark, fontFace: "Calibri", margin: 0,
      });
    });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 8 — COMPASS
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 8, TOTAL, "07  ·  COMPASS");

    s.addText("COMPASS — does the action serve the user's task?", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });
    s.addText("A session-level alignment oracle. Cosine similarity between the seeded user intent and the proposed action; drift below threshold is corroborating evidence.", {
      x: 0.5, y: 1.35, w: 12.3, h: 0.5,
      fontSize: 14, color: C.textMuted, italic: true, fontFace: "Calibri", margin: 0,
    });

    // Left: how it works diagram (vertical flow)
    const lx = 0.5, lw = 5.7;
    s.addShape("rect", { x: lx, y: 2.0, w: lw, h: 4.85,
      fill: { color: C.bgWhite }, line: { color: C.border, width: 1 } });
    s.addShape("rect", { x: lx, y: 2.0, w: lw, h: 0.45,
      fill: { color: C.gold }, line: { width: 0 } });
    s.addText("HOW IT WORKS", {
      x: lx + 0.2, y: 2.0, w: lw - 0.4, h: 0.45,
      fontSize: 12, color: C.navyDeep, bold: true, charSpacing: 4,
      valign: "middle", fontFace: "Calibri", margin: 0,
    });

    const flowSteps = [
      { lbl: "1", txt: "User message arrives — embed it as the intent vector v_intent" },
      { lbl: "2", txt: "Each proposed tool call → embed as v_action" },
      { lbl: "3", txt: "sim = cosine(v_intent, v_action)  ·  both BGE-normalized" },
      { lbl: "4", txt: "If sim < threshold → drift detected" },
      { lbl: "5", txt: "Threshold derived from data: Youden's J on 100 calibration pairs" },
    ];
    flowSteps.forEach((step, i) => {
      const sy = 2.7 + i * 0.78;
      s.addShape("ellipse", {
        x: lx + 0.25, y: sy, w: 0.45, h: 0.45,
        fill: { color: C.gold }, line: { width: 0 },
      });
      s.addText(step.lbl, {
        x: lx + 0.25, y: sy, w: 0.45, h: 0.45,
        fontSize: 14, color: C.navyDeep, bold: true,
        align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
      });
      s.addText(step.txt, {
        x: lx + 0.85, y: sy + 0.08, w: lw - 1.1, h: 0.5,
        fontSize: 12, color: C.textDark, fontFace: "Calibri", margin: 0,
      });
    });

    // Right: the example
    const rx = 6.6, rw = 6.3;
    s.addShape("rect", { x: rx, y: 2.0, w: rw, h: 4.85,
      fill: { color: C.bgWhite }, line: { color: C.border, width: 1 } });
    s.addShape("rect", { x: rx, y: 2.0, w: rw, h: 0.45,
      fill: { color: C.blue }, line: { width: 0 } });
    s.addText("WORKED EXAMPLE", {
      x: rx + 0.2, y: 2.0, w: rw - 0.4, h: 0.45,
      fontSize: 12, color: C.bgLite, bold: true, charSpacing: 4,
      valign: "middle", fontFace: "Calibri", margin: 0,
    });

    s.addText("USER", { x: rx + 0.25, y: 2.65, w: rw - 0.5, h: 0.25,
      fontSize: 10, color: C.textMuted, bold: true, charSpacing: 3,
      fontFace: "Calibri", margin: 0 });
    s.addShape("rect", { x: rx + 0.25, y: 2.95, w: rw - 0.5, h: 0.55,
      fill: { color: C.bgLite }, line: { color: C.border, width: 1 } });
    s.addText('"Help me debug a failing test in the parser module"', {
      x: rx + 0.4, y: 2.95, w: rw - 0.8, h: 0.55,
      fontSize: 12, color: C.textDark, italic: true, valign: "middle",
      fontFace: "Calibri", margin: 0,
    });

    s.addText("LATER, AGENT PROPOSES", { x: rx + 0.25, y: 3.7, w: rw - 0.5, h: 0.25,
      fontSize: 10, color: C.textMuted, bold: true, charSpacing: 3,
      fontFace: "Calibri", margin: 0 });
    s.addShape("rect", { x: rx + 0.25, y: 4.0, w: rw - 0.5, h: 0.55,
      fill: { color: C.bgLite }, line: { color: C.alert, width: 1.5 } });
    s.addText('tool:read_file  args:{"path":"/etc/shadow"}', {
      x: rx + 0.4, y: 4.0, w: rw - 0.8, h: 0.55,
      fontSize: 12, color: C.alert, valign: "middle",
      fontFace: "Consolas", margin: 0,
    });

    s.addText("COMPASS RESULT", { x: rx + 0.25, y: 4.75, w: rw - 0.5, h: 0.25,
      fontSize: 10, color: C.textMuted, bold: true, charSpacing: 3,
      fontFace: "Calibri", margin: 0 });
    s.addText([
      { text: "sim = ",      options: { color: C.textDark, fontFace: "Consolas", fontSize: 14 } },
      { text: "0.21",        options: { color: C.alert,     fontFace: "Consolas", fontSize: 18, bold: true } },
      { text: "  <  0.40 threshold  →  DRIFT",
        options: { color: C.alert, fontSize: 13, bold: true } },
    ], { x: rx + 0.25, y: 5.05, w: rw - 0.5, h: 0.45, fontFace: "Calibri", margin: 0 });

    s.addText("→ Speaker: ESCALATE if no minister blocks; BLOCK if any minister also flags borderline match.",
      { x: rx + 0.25, y: 5.55, w: rw - 0.5, h: 0.6,
        fontSize: 11, color: C.teal, italic: true,
        fontFace: "Calibri", margin: 0 });

    s.addText("Drift alone is never a hard block — the user might have legitimately pivoted. It's evidence, not the verdict.",
      { x: rx + 0.25, y: 6.2, w: rw - 0.5, h: 0.55,
        fontSize: 11, color: C.textMuted,
        fontFace: "Calibri", margin: 0 });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 9 — Speaker logic
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 9, TOTAL, "08  ·  SPEAKER");

    s.addText("The speaker — five rules, zero LLM calls, twelve tests", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });
    s.addText("Asymmetric and deny-first. One confident BLOCK from any minister suffices. No score averaging across ministers.", {
      x: 0.5, y: 1.35, w: 12.3, h: 0.5,
      fontSize: 14, color: C.textMuted, italic: true, fontFace: "Calibri", margin: 0,
    });

    // Five-row decision rule table (one row per case)
    const rules = [
      { case: "1", cond: "any minister BLOCK",                          drift: "—",       verdict: "BLOCK",    color: C.alert },
      { case: "2", cond: "any minister ESCALATE",                       drift: "drift",   verdict: "BLOCK",    color: C.alert },
      { case: "3", cond: "any minister ESCALATE",                       drift: "no drift",verdict: "ESCALATE", color: C.gold },
      { case: "4", cond: "all ministers ALLOW",                         drift: "drift",   verdict: "ESCALATE", color: C.gold },
      { case: "5", cond: "all ministers ALLOW",                         drift: "no drift",verdict: "ALLOW",    color: C.teal },
    ];

    // Header
    const tx = 0.5, tw = 12.3;
    s.addShape("rect", { x: tx, y: 2.05, w: tw, h: 0.5,
      fill: { color: C.navy }, line: { width: 0 } });

    const headers = [
      { l: "CASE",                  x: 0.55, w: 0.9 },
      { l: "MINISTERS SAY",         x: 1.55, w: 4.5 },
      { l: "COMPASS SAYS",          x: 6.15, w: 2.4 },
      { l: "VERDICT",               x: 8.65, w: 4.1 },
    ];
    headers.forEach(h => {
      s.addText(h.l, {
        x: h.x, y: 2.05, w: h.w, h: 0.5,
        fontSize: 10, color: C.bgLite, bold: true, charSpacing: 4,
        valign: "middle", fontFace: "Calibri", margin: 0,
      });
    });

    rules.forEach((r, i) => {
      const ry = 2.55 + i * 0.55;
      const fill = i % 2 === 0 ? C.bgWhite : C.bgLite;
      s.addShape("rect", { x: tx, y: ry, w: tw, h: 0.55,
        fill: { color: fill }, line: { color: C.border, width: 0.5 } });
      // Case
      s.addText(r.case, {
        x: 0.55, y: ry, w: 0.9, h: 0.55,
        fontSize: 16, color: C.textMuted, bold: true,
        align: "left", valign: "middle", fontFace: "Georgia", margin: 0,
      });
      // Ministers
      s.addText(r.cond, {
        x: 1.55, y: ry, w: 4.5, h: 0.55,
        fontSize: 13, color: C.textDark, valign: "middle",
        fontFace: "Calibri", margin: 0,
      });
      // COMPASS
      s.addText(r.drift, {
        x: 6.15, y: ry, w: 2.4, h: 0.55,
        fontSize: 13, color: r.drift === "drift" ? C.alert : C.textMuted,
        bold: r.drift === "drift", italic: r.drift === "—",
        valign: "middle", fontFace: "Calibri", margin: 0,
      });
      // Verdict pill
      s.addShape("roundRect", {
        x: 8.65, y: ry + 0.08, w: 1.6, h: 0.4,
        fill: { color: r.color }, line: { width: 0 },
        rectRadius: 0.05,
      });
      s.addText(r.verdict, {
        x: 8.65, y: ry + 0.08, w: 1.6, h: 0.4,
        fontSize: 11, color: C.bgLite, bold: true,
        align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
      });
    });

    // Bottom note
    s.addShape("rect", { x: 0.5, y: 5.6, w: 12.3, h: 1.25,
      fill: { color: C.bgWhite }, line: { color: C.border, width: 1 } });
    s.addImage({ data: ICONS.check, x: 0.7, y: 5.8, w: 0.4, h: 0.4 });
    s.addText("12 unit tests covering all five cases plus edge conditions", {
      x: 1.25, y: 5.7, w: 11, h: 0.4,
      fontSize: 16, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });
    s.addText("test_speaker.py — pure logic, no embedding model, no ChromaDB. Tests pin down the verdict logic so it cannot silently change. Runs in <100ms. All 12 currently passing.",
      { x: 1.25, y: 6.15, w: 11, h: 0.6,
        fontSize: 12, color: C.textMuted, fontFace: "Calibri", margin: 0 });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 10 — Corpus expansion protocol
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 10, TOTAL, "09  ·  CORPUS DISCIPLINE");

    s.addText("The expansion protocol — how we wrote 200 patterns blind", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });
    s.addText("Patterns sourced from MITRE ATT&CK technique IDs and OWASP Agentic 2026 categories — never from a CVE we'd seen, never with the InjecAgent benchmark visible.", {
      x: 0.5, y: 1.35, w: 12.3, h: 0.5,
      fontSize: 14, color: C.textMuted, italic: true, fontFace: "Calibri", margin: 0,
    });

    // Three-tier diagram showing L1 → L2 → L3 pattern structure
    const sx = 0.5, sw = 5.5;
    s.addShape("rect", { x: sx, y: 2.0, w: sw, h: 4.85,
      fill: { color: C.bgWhite }, line: { color: C.border, width: 1 } });
    s.addShape("rect", { x: sx, y: 2.0, w: sw, h: 0.45,
      fill: { color: C.blue }, line: { width: 0 } });
    s.addText("THREE LEVELS PER PATTERN", {
      x: sx + 0.2, y: 2.0, w: sw - 0.4, h: 0.45,
      fontSize: 11, color: C.bgLite, bold: true, charSpacing: 4,
      valign: "middle", fontFace: "Calibri", margin: 0,
    });

    const tiers = [
      { lbl: "L1", name: "Intent",     desc: "What the agent is trying to do. No tool names, no syntax. Catches novel implementations.", color: C.teal },
      { lbl: "L2", name: "Mechanism",  desc: "What category of mechanism is used. May reference tool classes (e.g. 'package manager') but not specific commands.", color: C.blue },
      { lbl: "L3", name: "Surface",    desc: "What it looks like at the API/syntax layer. Specific tool names, command flags, paths allowed here.", color: C.goldDeep },
    ];

    tiers.forEach((t, i) => {
      const ty = 2.7 + i * 1.35;
      // Block tag on left
      s.addShape("roundRect", {
        x: sx + 0.25, y: ty, w: 0.6, h: 0.6,
        fill: { color: t.color }, line: { width: 0 }, rectRadius: 0.05,
      });
      s.addText(t.lbl, {
        x: sx + 0.25, y: ty, w: 0.6, h: 0.6,
        fontSize: 18, color: C.bgLite, bold: true, fontFace: "Georgia",
        align: "center", valign: "middle", margin: 0,
      });
      s.addText(t.name, {
        x: sx + 1.0, y: ty - 0.05, w: sw - 1.2, h: 0.4,
        fontSize: 16, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
      });
      s.addText(t.desc, {
        x: sx + 1.0, y: ty + 0.32, w: sw - 1.2, h: 0.85,
        fontSize: 11, color: C.textDark, fontFace: "Calibri", margin: 0,
      });
    });

    // Right column: the 8 protocol rules (compact)
    const rx = 6.4, rw = 6.5;
    s.addShape("rect", { x: rx, y: 2.0, w: rw, h: 4.85,
      fill: { color: C.bgWhite }, line: { color: C.border, width: 1 } });
    s.addShape("rect", { x: rx, y: 2.0, w: rw, h: 0.45,
      fill: { color: C.alert }, line: { width: 0 } });
    s.addText("EIGHT NON-NEGOTIABLE RULES", {
      x: rx + 0.2, y: 2.0, w: rw - 0.4, h: 0.45,
      fontSize: 11, color: C.bgLite, bold: true, charSpacing: 4,
      valign: "middle", fontFace: "Calibri", margin: 0,
    });

    const rules = [
      "No CVE, no ClawHavoc, no InjecAgent visible during writing",
      "Source-first: cite a MITRE technique ID, not a known incident",
      "Write L1 → L2 → L3 in order. Top-down forces honesty.",
      "The \"tomorrow test\" — would L1 catch a novel tool achieving the same intent?",
      "The \"blue team test\" — can a benign script trigger this? If yes, rewrite.",
      "No collaboration during writing; swap files for review",
      "One pattern, one intent. No \"and\" connecting two verbs in L1.",
      "Cite freshly — at most one MITRE technique + one OWASP/CWE",
    ];
    rules.forEach((r, i) => {
      const ry = 2.62 + i * 0.52;
      s.addText(String(i + 1).padStart(2, "0"), {
        x: rx + 0.25, y: ry, w: 0.5, h: 0.4,
        fontSize: 14, color: C.alert, bold: true, fontFace: "Georgia", margin: 0,
      });
      s.addText(r, {
        x: rx + 0.85, y: ry, w: rw - 1.1, h: 0.5,
        fontSize: 11, color: C.textDark, fontFace: "Calibri", margin: 0,
      });
    });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 11 — By the numbers (corpus stats with chart)
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 11, TOTAL, "10  ·  CORPUS BY THE NUMBERS");

    s.addText("Where we stand — corpus v2 status", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });

    // Big stat callouts at top
    const stats = [
      { num: "200", lbl: "new v2 patterns",    sub: "50 per minister × 4",     color: C.blueDeep },
      { num: "600", lbl: "embedded documents", sub: "L1 + L2 + L3 per pattern",color: C.blueDeep },
      { num: "0",   lbl: "validation rejects", sub: "merge passes clean",       color: C.teal },
      { num: "12 / 12", lbl: "speaker tests pass", sub: "verdict logic pinned",color: C.teal },
    ];
    stats.forEach((st, i) => {
      const x = 0.5 + i * 3.2;
      s.addShape("rect", {
        x, y: 1.55, w: 3.0, h: 1.4,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 },
      });
      s.addShape("rect", { x, y: 1.55, w: 3.0, h: 0.06,
        fill: { color: st.color }, line: { width: 0 } });
      s.addText(st.num, {
        x: x + 0.15, y: 1.7, w: 2.7, h: 0.7,
        fontSize: 44, color: st.color, bold: true,
        fontFace: "Georgia", align: "left", margin: 0,
      });
      s.addText(st.lbl, {
        x: x + 0.15, y: 2.4, w: 2.7, h: 0.3,
        fontSize: 12, color: C.navy, bold: true, fontFace: "Calibri", margin: 0,
      });
      s.addText(st.sub, {
        x: x + 0.15, y: 2.7, w: 2.7, h: 0.25,
        fontSize: 10, color: C.textMuted, fontFace: "Calibri", margin: 0,
      });
    });

    // Chart: patterns per minister stacked by abstraction level
    s.addText("Pattern distribution per minister  ·  v2 corpus", {
      x: 0.5, y: 3.25, w: 12.3, h: 0.4,
      fontSize: 16, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });
    s.addChart(pres.charts.BAR, [
      { name: "v1 patterns",    labels: ["EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR"], values: [50, 50, 50, 50] },
      { name: "v2 (new)",       labels: ["EXECUTOR", "VAULT", "CHANNEL", "NAVIGATOR"], values: [50, 50, 50, 50] },
    ], {
      x: 0.5, y: 3.7, w: 7.5, h: 3.1,
      barDir: "col", barGrouping: "stacked",
      chartColors: [C.blueLite, C.blueDeep],
      chartArea: { fill: { color: C.bgWhite }, roundedCorners: false },
      catAxisLabelColor: C.navy, catAxisLabelFontSize: 11,
      valAxisLabelColor: C.textMuted, valAxisLabelFontSize: 10,
      valGridLine: { color: C.border, size: 0.5 },
      catGridLine: { style: "none" },
      showLegend: true, legendPos: "b", legendFontSize: 11, legendColor: C.textDark,
      showValue: true, dataLabelFontSize: 10, dataLabelColor: C.bgLite,
    });

    // Right side — sources composition
    s.addShape("rect", {
      x: 8.3, y: 3.7, w: 4.6, h: 3.1,
      fill: { color: C.bgWhite }, line: { color: C.border, width: 1 },
    });
    s.addText("SOURCE TAXONOMIES", {
      x: 8.45, y: 3.8, w: 4.4, h: 0.25,
      fontSize: 10, color: C.textMuted, bold: true, charSpacing: 3,
      fontFace: "Calibri", margin: 0,
    });
    const sources = [
      { lbl: "MITRE ATT&CK",       count: "63 unique technique IDs", icon: ICONS.shieldNavy },
      { lbl: "OWASP Agentic 2026", count: "all six A0X categories",   icon: ICONS.shieldNavy },
      { lbl: "CWE",                count: "11 weakness classes",     icon: ICONS.shieldNavy },
      { lbl: "Citation breadth",   count: "no source > 12 patterns", icon: ICONS.shieldNavy },
    ];
    sources.forEach((src, i) => {
      const sy = 4.1 + i * 0.65;
      s.addImage({ data: src.icon, x: 8.5, y: sy + 0.08, w: 0.3, h: 0.3 });
      s.addText(src.lbl, {
        x: 8.95, y: sy, w: 3.9, h: 0.3,
        fontSize: 12, color: C.navy, bold: true, fontFace: "Calibri", margin: 0,
      });
      s.addText(src.count, {
        x: 8.95, y: sy + 0.28, w: 3.9, h: 0.3,
        fontSize: 11, color: C.textMuted, fontFace: "Calibri", margin: 0,
      });
    });

    // Bottom note
    s.addText("Validator: word-bounded reject list catches L1 tool-name leakage. Two real protocol violations found in our own writing during the merge — fixed before commit.",
      { x: 0.5, y: 6.92, w: 8.4, h: 0.3,
        fontSize: 10, color: C.textMuted, italic: true, align: "left",
        fontFace: "Calibri", margin: 0 });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 12 — Validation gates (10-step reproducibility)
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 12, TOTAL, "11  ·  VALIDATION GATES");

    s.addText("The ten-step validation sequence", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });
    s.addText("Run in order. Each step has a pass condition. Skipping or reordering produces benchmark numbers that don't mean what we'll claim they mean.", {
      x: 0.5, y: 1.35, w: 12.3, h: 0.5,
      fontSize: 14, color: C.textMuted, italic: true, fontFace: "Calibri", margin: 0,
    });

    const steps = [
      { n: "0",  lbl: "Environment",      desc: "venv + pip install requirements.txt" },
      { n: "1",  lbl: "Merge corpus",     desc: "v1 + v2 → kavach_corpus_v2.json (zero rejects)" },
      { n: "2",  lbl: "Load ChromaDB",    desc: "5 collections, ~600 docs, BGE mean pooling" },
      { n: "3",  lbl: "Calibrate COMPASS",desc: "Youden's J on 100 pairs → threshold updated" },
      { n: "4",  lbl: "Smoke test",       desc: "7 end-to-end checks; latency p95 < 300ms" },
      { n: "5",  lbl: "Benign FPR gate",  desc: "≤ 5% on 50 hand-curated benign sessions", critical: true },
      { n: "6",  lbl: "InjecAgent run",   desc: "1054 cases cold; record verdict + latency" },
      { n: "7",  lbl: "Threshold sweep",  desc: "ROC + Youden's J per minister" },
      { n: "8",  lbl: "OpenClaw demo",    desc: "ClawHavoc-style attack blocked at tool boundary" },
      { n: "9",  lbl: "Latency budget",   desc: "p50/p95/p99 by stage for the paper" },
    ];

    // 5 cards × 2 rows
    steps.forEach((st, i) => {
      const col = i % 5, row = Math.floor(i / 5);
      const x = 0.5 + col * 2.5;
      const y = 2.05 + row * 2.4;
      const w = 2.35, h = 2.2;
      const accent = st.critical ? C.alert : C.blue;

      s.addShape("rect", {
        x, y, w, h,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 },
      });
      s.addShape("rect", { x, y, w, h: 0.06,
        fill: { color: accent }, line: { width: 0 } });
      // Step number
      s.addText(st.n, {
        x, y: y + 0.15, w, h: 0.7,
        fontSize: 36, color: accent, bold: true, align: "center",
        fontFace: "Georgia", margin: 0,
      });
      s.addText(st.lbl, {
        x: x + 0.12, y: y + 0.95, w: w - 0.24, h: 0.4,
        fontSize: 13, color: C.navy, bold: true, align: "center",
        fontFace: "Georgia", margin: 0,
      });
      s.addText(st.desc, {
        x: x + 0.15, y: y + 1.35, w: w - 0.3, h: 0.7,
        fontSize: 10, color: C.textDark, align: "center",
        fontFace: "Calibri", margin: 0,
      });
      // Critical-step badge
      if (st.critical) {
        s.addShape("roundRect", {
          x: x + w - 0.95, y: y + 0.1, w: 0.85, h: 0.25,
          fill: { color: C.alert }, line: { width: 0 }, rectRadius: 0.04,
        });
        s.addText("HARD GATE", {
          x: x + w - 0.95, y: y + 0.1, w: 0.85, h: 0.25,
          fontSize: 8, color: C.bgLite, bold: true, charSpacing: 2,
          align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
        });
      }
    });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 13 — Why benign-FPR runs before InjecAgent
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 13, TOTAL, "12  ·  THE BENIGN FPR GATE");

    s.addText("Why we run 50 benign sessions before InjecAgent", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 28, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });

    // Top: the failure mode if you skip the gate
    s.addShape("rect", { x: 0.5, y: 1.35, w: 12.3, h: 1.0,
      fill: { color: C.bgWhite }, line: { color: C.alert, width: 1.5 } });
    s.addImage({ data: ICONS.warn, x: 0.7, y: 1.55, w: 0.6, h: 0.6 });
    s.addText("THE FAILURE MODE WE'RE AVOIDING", {
      x: 1.5, y: 1.45, w: 11, h: 0.3,
      fontSize: 11, color: C.alert, bold: true, charSpacing: 4,
      fontFace: "Calibri", margin: 0,
    });
    s.addText("If you run InjecAgent on a corpus that hasn't passed FPR validation, you get a recall number that conflates detector quality with detector aggressiveness. A 95% recall at 30% FPR is sophisticated keyword matching, not semantic understanding. The InjecAgent number ceases to mean anything publishable.",
      { x: 1.5, y: 1.75, w: 10.7, h: 0.6,
        fontSize: 12, color: C.textDark, fontFace: "Calibri", margin: 0 });

    // Three columns: what benign traces look like, how the gate works, what we do if it fails
    const cols = [
      {
        x: 0.5, head: "WHAT'S IN THE 50 SESSIONS", color: C.blueDeep, icon: ICONS.list,
        items: [
          "code editing — docstrings, type hints, refactors",
          "build & test — pytest, npm build, mypy",
          "git operations — status, diff, commit, branch",
          "package management — pip install, npm install",
          "infrastructure — docker build, alembic upgrade",
          "operations — kubectl context, aws s3 ls, curl health",
          "debugging — read logs, run profiler, tail -f",
          "documentation — sphinx-build, README updates",
        ],
      },
      {
        x: 4.7, head: "THE GATE LOGIC", color: C.gold, icon: ICONS.gavel,
        items: [
          "seed_intent for each session",
          "replay each tool call through /hook/parliament",
          "record verdict + matched pattern + minister",
          "compute fpr_block_only and fpr_block_or_escalate",
          "if fpr > 5% → STOP and read blocked_actions.txt",
          "blocked_actions.txt names every wrongly-blocked call and the matched pattern",
          "fix the over-aggressive patterns per the protocol",
          "re-run until gate passes",
        ],
      },
      {
        x: 8.9, head: "WHAT FAILS LIKELY MEANS", color: C.alert, icon: ICONS.bug,
        items: [
          "L3 too specific — matches benign syntax that overlaps with attack syntax",
          "L1 too broad — \"agent invokes a shell command\" applies to every legit code agent",
          "Missing constraint on provenance — capture only when content originates from network bytes",
          "Source citation too generic — pattern is two intents merged",
          "These rewrites are documented in the corpus changelog",
          "The iteration count itself becomes a §7 limitation finding",
        ],
      },
    ];

    cols.forEach(c => {
      s.addShape("rect", { x: c.x, y: 2.55, w: 4.0, h: 4.3,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 } });
      s.addShape("rect", { x: c.x, y: 2.55, w: 4.0, h: 0.08,
        fill: { color: c.color }, line: { width: 0 } });
      s.addImage({ data: c.icon, x: c.x + 0.25, y: 2.78, w: 0.35, h: 0.35 });
      s.addText(c.head, {
        x: c.x + 0.7, y: 2.75, w: 3.2, h: 0.45,
        fontSize: 11, color: c.color, bold: true, charSpacing: 4,
        valign: "middle", fontFace: "Calibri", margin: 0,
      });
      const itemRuns = c.items.map((it, i) => ({
        text: it, options: { bullet: true, breakLine: i < c.items.length - 1, paraSpaceAfter: 6 },
      }));
      s.addText(itemRuns, {
        x: c.x + 0.25, y: 3.3, w: 3.6, h: 3.5,
        fontSize: 10, color: C.textDark, fontFace: "Calibri", margin: 0,
        valign: "top",
      });
    });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 14 — Where the numbers will come from
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 14, TOTAL, "13  ·  PATH TO REAL NUMBERS");

    s.addText("Where the §5 numbers will come from", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });
    s.addText("Three datasets, three measurements, one cold-recall claim. The numbers don't exist yet — but the harness that produces them does.", {
      x: 0.5, y: 1.35, w: 12.3, h: 0.5,
      fontSize: 14, color: C.textMuted, italic: true, fontFace: "Calibri", margin: 0,
    });

    const datasets = [
      {
        x: 0.5, head: "InjecAgent (UIUC, 2024)", icon: ICONS.flask, color: C.blueDeep,
        n: "1,054", nLbl: "test cases", what: "Prompt-injection attack cases: benign user instruction + malicious tool output + expected attacker action.",
        why: "Standard benchmark for tool-call interception. Cold run — corpus authors had not seen the test set.",
        produces: "BLOCK recall, FPR, F1, p95 latency",
      },
      {
        x: 4.7, head: "Hand-curated benign traces", icon: ICONS.book, color: C.teal,
        n: "50", nLbl: "agent sessions", what: "Code editing, build, debug, git, deployment — written by hand to be representative of legit work.",
        why: "Gates the InjecAgent run. Without this, recall is meaningless.",
        produces: "FPR by category, blocked_actions.txt for review",
      },
      {
        x: 8.9, head: "COMPASS calibration set", icon: ICONS.compass, color: C.gold,
        n: "100", nLbl: "intent / action pairs", what: "Aligned and drifted intent-action pairs. Shipped with the v1 corpus.",
        why: "Derives the COMPASS drift threshold via Youden's J — not gut feel.",
        produces: "Calibrated threshold, ROC histogram, distribution stats",
      },
    ];

    datasets.forEach(d => {
      s.addShape("rect", { x: d.x, y: 2.0, w: 4.0, h: 4.85,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 } });
      s.addShape("rect", { x: d.x, y: 2.0, w: 4.0, h: 0.45,
        fill: { color: d.color }, line: { width: 0 } });
      s.addImage({ data: d.icon, x: d.x + 0.2, y: 2.07, w: 0.3, h: 0.3 });
      s.addText(d.head, {
        x: d.x + 0.6, y: 2.0, w: 3.4, h: 0.45,
        fontSize: 12, color: C.bgLite, bold: true,
        valign: "middle", fontFace: "Calibri", margin: 0,
      });

      // Big N
      s.addText(d.n, {
        x: d.x + 0.25, y: 2.6, w: 3.5, h: 0.85,
        fontSize: 48, color: d.color, bold: true,
        fontFace: "Georgia", margin: 0,
      });
      s.addText(d.nLbl, {
        x: d.x + 0.25, y: 3.45, w: 3.5, h: 0.3,
        fontSize: 12, color: C.textMuted, fontFace: "Calibri", margin: 0,
      });

      s.addText("WHAT IT IS", {
        x: d.x + 0.25, y: 3.85, w: 3.5, h: 0.25,
        fontSize: 9, color: C.textMuted, bold: true, charSpacing: 3,
        fontFace: "Calibri", margin: 0,
      });
      s.addText(d.what, {
        x: d.x + 0.25, y: 4.1, w: 3.5, h: 0.85,
        fontSize: 10, color: C.textDark, fontFace: "Calibri", margin: 0,
      });
      s.addText("WHY", {
        x: d.x + 0.25, y: 5.0, w: 3.5, h: 0.25,
        fontSize: 9, color: C.textMuted, bold: true, charSpacing: 3,
        fontFace: "Calibri", margin: 0,
      });
      s.addText(d.why, {
        x: d.x + 0.25, y: 5.25, w: 3.5, h: 0.75,
        fontSize: 10, color: C.textDark, fontFace: "Calibri", margin: 0,
      });
      s.addText("PRODUCES", {
        x: d.x + 0.25, y: 6.05, w: 3.5, h: 0.25,
        fontSize: 9, color: C.textMuted, bold: true, charSpacing: 3,
        fontFace: "Calibri", margin: 0,
      });
      s.addText(d.produces, {
        x: d.x + 0.25, y: 6.3, w: 3.5, h: 0.5,
        fontSize: 10, color: d.color, italic: true, fontFace: "Calibri", margin: 0,
      });
    });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 15 — Paper status
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 15, TOTAL, "14  ·  PAPER STATUS");

    s.addText("Paper draft — what's written, what's pending", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });
    s.addText("Two of the eight sections are fully drafted. The remaining sections either need numbers (§5) or are short stubs (§6, §7, §8) that fill in once benchmarks land.", {
      x: 0.5, y: 1.35, w: 12.3, h: 0.5,
      fontSize: 14, color: C.textMuted, italic: true, fontFace: "Calibri", margin: 0,
    });

    // Section status table
    const sections = [
      { id: "§1", title: "Introduction",                     status: "DRAFTED",  color: C.teal,  detail: "Full prose. Motivation, three contributions, scope, reproducibility commitment." },
      { id: "§2", title: "Background",                       status: "STUB",     color: C.gold,  detail: "Outline of agent attack surface and existing guardrails. Easy to fill, no number deps." },
      { id: "§3", title: "Kavach Architecture",              status: "STUB",     color: C.gold,  detail: "Diagram + minister table + speaker description. Mostly mechanical writeup." },
      { id: "§4", title: "Temporal-vs-Spatial Defense-in-Depth", status: "DRAFTED",  color: C.teal,  detail: "The strongest novel contribution — formal defs, necessity claim, coverage theorem." },
      { id: "§5", title: "Evaluation",                       status: "PENDING",  color: C.alert, detail: "Awaiting benchmark numbers from Workstream D. Skeleton in place." },
      { id: "§6", title: "Related Work",                     status: "DRAFTED",  color: C.teal,  detail: "12 paragraphs in related_work.md, each with explicit differentiation." },
      { id: "§7", title: "Limitations",                      status: "STUB",     color: C.gold,  detail: "Honest about overfitting story, single-vector cosine ceiling, minister independence untested." },
      { id: "§8", title: "Future Work",                      status: "STUB",     color: C.gold,  detail: "CORTEX, SUPPLY, federated corpus, MCP-Security spec." },
    ];

    sections.forEach((sec, i) => {
      const col = i % 2, row = Math.floor(i / 2);
      const x = 0.5 + col * 6.35;
      const y = 2.0 + row * 1.18;
      const w = 6.0, h = 1.05;

      s.addShape("rect", { x, y, w, h,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 } });

      // Section ID
      s.addText(sec.id, {
        x: x + 0.15, y: y + 0.15, w: 0.8, h: 0.8,
        fontSize: 24, color: C.navy, bold: true, fontFace: "Georgia",
        align: "center", valign: "middle", margin: 0,
      });
      // Title
      s.addText(sec.title, {
        x: x + 0.95, y: y + 0.1, w: w - 2.55, h: 0.4,
        fontSize: 14, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
      });
      // Status pill
      s.addShape("roundRect", {
        x: x + w - 1.45, y: y + 0.18, w: 1.3, h: 0.32,
        fill: { color: sec.color }, line: { width: 0 }, rectRadius: 0.04,
      });
      s.addText(sec.status, {
        x: x + w - 1.45, y: y + 0.18, w: 1.3, h: 0.32,
        fontSize: 9, color: C.bgLite, bold: true, charSpacing: 3,
        align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
      });
      // Detail
      s.addText(sec.detail, {
        x: x + 0.95, y: y + 0.5, w: w - 1.1, h: 0.55,
        fontSize: 10, color: C.textMuted, fontFace: "Calibri", margin: 0,
      });
    });

    // Bottom: target venues
    s.addShape("rect", { x: 0.5, y: 6.85, w: 12.3, h: 0.4,
      fill: { color: C.navy }, line: { width: 0 } });
    s.addText([
      { text: "TARGET VENUES   ", options: { color: C.blueLite, bold: true, charSpacing: 3, fontSize: 10 } },
      { text: "ICML 2026 Workshop  →  MASEC@NeurIPS 2026  →  SaTML 2027",
        options: { color: C.bgLite, fontSize: 11 } },
    ], { x: 0.5, y: 6.85, w: 12.3, h: 0.4,
        align: "center", valign: "middle", fontFace: "Calibri", margin: 0 });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 16 — Workstream status
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 16, TOTAL, "15  ·  WORKSTREAM STATUS");

    s.addText("Where each workstream stands", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });

    const workstreams = [
      {
        ws: "A", title: "OpenClaw PR-1",            owner: "Parv + Ishani",
        progress: 60, status: "spec ready", color: C.alert,
        what: "Patch for #5513 + #5943 with vitest regressions written. Awaiting upstream review.",
      },
      {
        ws: "B", title: "Parliament FastAPI service", owner: "Ishani",
        progress: 90, status: "code complete", color: C.teal,
        what: "Service runs. Smoke test passes against synthetic. Needs lab run against full corpus.",
      },
      {
        ws: "C", title: "Corpus generalization (200 patterns)", owner: "Janya + Pranitha",
        progress: 75, status: "written, pending review", color: C.gold,
        what: "All 200 v2 patterns drafted, merge clean. Cross-review by writer-swap not yet done.",
      },
      {
        ws: "D", title: "InjecAgent + benign FPR benchmark", owner: "Janya",
        progress: 50, status: "harness ready", color: C.gold,
        what: "Runner, threshold sweep, benign traces all written. Cannot run until B and C complete.",
      },
      {
        ws: "E", title: "Paper draft",              owner: "Jamieboy",
        progress: 35, status: "§1 + §4 drafted", color: C.gold,
        what: "Strongest sections already prose-complete. §5 pending Workstream D numbers.",
      },
    ];

    workstreams.forEach((w, i) => {
      const y = 1.7 + i * 1.05;

      // Card
      s.addShape("rect", { x: 0.5, y, w: 12.3, h: 0.95,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 } });

      // Workstream tag
      s.addShape("rect", { x: 0.5, y, w: 0.8, h: 0.95,
        fill: { color: C.navy }, line: { width: 0 } });
      s.addText(w.ws, {
        x: 0.5, y, w: 0.8, h: 0.95,
        fontSize: 36, color: C.bgLite, bold: true,
        align: "center", valign: "middle", fontFace: "Georgia", margin: 0,
      });

      // Title + owner
      s.addText(w.title, {
        x: 1.5, y: y + 0.1, w: 5.5, h: 0.35,
        fontSize: 14, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
      });
      s.addText("OWNER  ·  " + w.owner, {
        x: 1.5, y: y + 0.45, w: 5.5, h: 0.25,
        fontSize: 9, color: C.textMuted, charSpacing: 3,
        fontFace: "Calibri", margin: 0,
      });
      s.addText(w.what, {
        x: 1.5, y: y + 0.65, w: 5.5, h: 0.3,
        fontSize: 10, color: C.textDark, fontFace: "Calibri", margin: 0,
      });

      // Progress bar
      const pBarX = 7.3, pBarW = 4.0, pBarY = y + 0.45, pBarH = 0.3;
      s.addShape("rect", { x: pBarX, y: pBarY, w: pBarW, h: pBarH,
        fill: { color: C.bgLite }, line: { color: C.border, width: 0.5 } });
      s.addShape("rect", { x: pBarX, y: pBarY, w: pBarW * w.progress / 100, h: pBarH,
        fill: { color: w.color }, line: { width: 0 } });
      s.addText(w.progress + "%", {
        x: pBarX, y: pBarY, w: pBarW, h: pBarH,
        fontSize: 11, color: C.navy, bold: true,
        align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
      });
      s.addText(w.status, {
        x: pBarX, y: y + 0.78, w: pBarW, h: 0.2,
        fontSize: 9, color: w.color, italic: true, bold: true,
        align: "center", fontFace: "Calibri", margin: 0,
      });

      // Status badge on right
      s.addShape("rect", { x: 11.5, y, w: 1.3, h: 0.95,
        fill: { color: w.color }, line: { width: 0 } });
      const statusLabel = w.progress >= 80 ? "ON TRACK"
                       : (w.progress >= 50 ? "IN PROGRESS"
                       : "EARLY");
      s.addText(statusLabel, {
        x: 11.5, y, w: 1.3, h: 0.95,
        fontSize: 11, color: C.bgLite, bold: true, charSpacing: 3,
        align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
      });
    });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 17 — 4-week burndown
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 17, TOTAL, "16  ·  THE FOUR-WEEK PLAN");

    s.addText("What's left — week-by-week", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });

    const weeks = [
      {
        n: "WEEK 1",
        title: "Land the interception fix",
        items: [
          "Open PR-1 against OpenClaw upstream",
          "Comment on Discussion #9872",
          "Stand up parliament/server.py against the v2 corpus",
          "Write second-half VAULT/CHANNEL/NAVIGATOR patterns (cross-review)",
        ],
        color: C.alert,
      },
      {
        n: "WEEK 2",
        title: "Lab run + corpus iteration",
        items: [
          "Re-load corpus, re-run COMPASS calibration with real data",
          "Run benign-FPR gate; iterate until ≤ 5%",
          "If PR-1 stalls, ship monkey-patch in plugin npm package",
          "Apply PR-1 patch locally to unblock end-to-end demo",
        ],
        color: C.gold,
      },
      {
        n: "WEEK 3",
        title: "Get real benchmark numbers",
        items: [
          "Run InjecAgent (cold, no corpus tuning)",
          "Threshold sweep + ROC plots",
          "End-to-end attack demo through the OpenClaw plugin",
          "Latency budget breakdown by pipeline stage",
        ],
        color: C.blueDeep,
      },
      {
        n: "WEEK 4",
        title: "Paper writeup + demo prep",
        items: [
          "Fill §5 with the numbers; tighten §1 and §4",
          "Write §3 and §7 — limitations honestly",
          "Prepare next capstone-review demo",
          "Workshop submission packet (ICML 2026 workshop)",
        ],
        color: C.teal,
      },
    ];

    weeks.forEach((w, i) => {
      const x = 0.5 + i * 3.2;
      const y = 1.85;
      const ww = 3.0, wh = 5.0;

      s.addShape("rect", { x, y, w: ww, h: wh,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 } });
      // Top accent
      s.addShape("rect", { x, y, w: ww, h: 0.7,
        fill: { color: w.color }, line: { width: 0 } });
      s.addText(w.n, {
        x: x + 0.2, y: y + 0.05, w: ww - 0.4, h: 0.3,
        fontSize: 11, color: C.bgLite, bold: true, charSpacing: 4,
        fontFace: "Calibri", margin: 0,
      });
      s.addText(w.title, {
        x: x + 0.2, y: y + 0.32, w: ww - 0.4, h: 0.4,
        fontSize: 13, color: C.bgLite, bold: true, italic: true,
        fontFace: "Calibri", margin: 0,
      });

      // Items
      const itemRuns = w.items.map((it, idx) => ({
        text: it, options: { bullet: true, breakLine: idx < w.items.length - 1, paraSpaceAfter: 8 },
      }));
      s.addText(itemRuns, {
        x: x + 0.2, y: y + 0.9, w: ww - 0.4, h: wh - 1.05,
        fontSize: 11, color: C.textDark, fontFace: "Calibri", margin: 0,
        valign: "top",
      });
    });

    // Bottom: critical-path arrow
    s.addText("CRITICAL PATH  ·  Week 1 PR-1 must land before Week 2 can run a meaningful benign gate, before Week 3 can run InjecAgent.", {
      x: 0.5, y: 6.92, w: 8.4, h: 0.3,
      fontSize: 10, color: C.textMuted, italic: true, align: "left",
      charSpacing: 2, fontFace: "Calibri", margin: 0,
    });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 18 — Demo plan for the next review
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 18, TOTAL, "17  ·  NEXT REVIEW DEMO");

    s.addText("What we'll show at the next capstone review", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });
    s.addText("The demo equivalent of April's ClawHavoc playback — but with pre-execution interception instead of post-hoc detection.", {
      x: 0.5, y: 1.35, w: 12.3, h: 0.5,
      fontSize: 14, color: C.textMuted, italic: true, fontFace: "Calibri", margin: 0,
    });

    // Storyboard: 4 panels left-to-right
    const panels = [
      {
        n: "1", title: "Setup",
        body: "Three terminals — parliament, OpenClaw with Kavach plugin loaded, attack sender. Show the parliament's /health endpoint reporting all five collections loaded.",
        icon: ICONS.server,
      },
      {
        n: "2", title: "Send the attack",
        body: "User-style prompt: \"install the dependencies for this skill.\" The skill's prerequisites contain a curl-pipe-bash, ClawHavoc-style. Send it through OpenClaw.",
        icon: ICONS.bug,
      },
      {
        n: "3", title: "Watch the parliament fire",
        body: "EXECUTOR matches at sim ≥ 0.8 against EXEC-051 or similar. Speaker returns BLOCK with reason. Plugin honors deny-first. The tool does NOT execute.",
        icon: ICONS.gavel,
      },
      {
        n: "4", title: "Show the ledger row",
        body: "sqlite3 parliament/kavach_parliament.db — one row, BLOCK verdict, decided_by EXECUTOR, the matched pattern ID, the latency in ms, the correlation ID.",
        icon: ICONS.db,
      },
    ];

    panels.forEach((p, i) => {
      const x = 0.5 + i * 3.2;
      const y = 2.0;
      const w = 3.0, h = 4.4;

      s.addShape("rect", { x, y, w, h,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 } });
      // Number circle
      s.addShape("ellipse", {
        x: x + w/2 - 0.4, y: y + 0.3, w: 0.8, h: 0.8,
        fill: { color: C.navy }, line: { width: 0 },
      });
      s.addText(p.n, {
        x: x + w/2 - 0.4, y: y + 0.3, w: 0.8, h: 0.8,
        fontSize: 28, color: C.bgLite, bold: true,
        align: "center", valign: "middle", fontFace: "Georgia", margin: 0,
      });
      // Icon
      s.addImage({ data: p.icon, x: x + w/2 - 0.3, y: y + 1.3, w: 0.6, h: 0.6 });
      // Title
      s.addText(p.title, {
        x: x + 0.2, y: y + 2.0, w: w - 0.4, h: 0.4,
        fontSize: 16, color: C.navy, bold: true, align: "center",
        fontFace: "Georgia", margin: 0,
      });
      // Body
      s.addText(p.body, {
        x: x + 0.2, y: y + 2.45, w: w - 0.4, h: 1.85,
        fontSize: 11, color: C.textDark, align: "left",
        fontFace: "Calibri", margin: 0,
      });
    });

    // Bottom call-out
    s.addShape("rect", { x: 0.5, y: 6.55, w: 12.3, h: 0.45,
      fill: { color: C.navy }, line: { width: 0 } });
    s.addText("If we can produce that ledger row without the attack having run — Kavach is a real guardrail. That's Figure 1 of the paper.", {
      x: 0.5, y: 6.55, w: 12.3, h: 0.45,
      fontSize: 12, color: C.bgLite, italic: true, bold: true,
      align: "center", valign: "middle", fontFace: "Georgia", margin: 0,
    });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 19 — Asks
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    chrome(s, 19, TOTAL, "18  ·  WHAT WE NEED");

    s.addText("Asks of the advisor and the team", {
      x: 0.5, y: 0.6, w: 12.3, h: 0.7,
      fontSize: 30, color: C.navy, bold: true, fontFace: "Georgia", margin: 0,
    });

    // Two columns: ask-of-advisor / ask-of-team
    const cols = [
      {
        x: 0.5, head: "FROM SIR / GUIDE", color: C.blueDeep, icon: ICONS.userShield,
        items: [
          { l: "Lab access in 20 days as planned.",
            d: "We have the tooling ready; we cannot run any benchmark numbers without the GPU." },
          { l: "Sign off on the venue plan.",
            d: "ICML 2026 Workshop on Agents in the Wild (May/June, non-archival) → MASEC@NeurIPS 2026 → SaTML 2027 archival." },
          { l: "Feedback on §1 and §4 prose.",
            d: "Both are drafted in paper/section_*.tex. The temporal-vs-spatial distinction in §4 is the strongest theoretical claim — worth a careful read." },
          { l: "Agreement that the benign-FPR gate is non-negotiable.",
            d: "If we ship InjecAgent numbers without it and a reviewer asks, we have no defense." },
        ],
      },
      {
        x: 6.85, head: "FROM THE TEAM", color: C.teal, icon: ICONS.users,
        items: [
          { l: "Cross-review of the v2 patterns.",
            d: "Janya reviews Pranitha's, Pranitha reviews Janya's. If the reviewer can identify the writer from style, the patterns are too writer-specific." },
          { l: "Parv: open PR-1 to OpenClaw upstream.",
            d: "Spec is in openclaw_pr/PR1_hooks_fix.md. Two test files ready as the PR's first commit." },
          { l: "Ishani: bring the parliament up against full v2 corpus.",
            d: "Run smoke_test.py first, only then proceed to benchmarks." },
          { l: "Agreement on the publishing plan.",
            d: "Repo private until Workstream C cross-review and Workstream D benign gate both pass. Then make public." },
        ],
      },
    ];

    cols.forEach(c => {
      s.addShape("rect", { x: c.x, y: 1.7, w: 6.0, h: 5.15,
        fill: { color: C.bgWhite }, line: { color: C.border, width: 1 } });
      s.addShape("rect", { x: c.x, y: 1.7, w: 6.0, h: 0.55,
        fill: { color: c.color }, line: { width: 0 } });
      s.addImage({ data: c.icon, x: c.x + 0.25, y: 1.83, w: 0.3, h: 0.3 });
      s.addText(c.head, {
        x: c.x + 0.7, y: 1.7, w: 5.2, h: 0.55,
        fontSize: 13, color: C.bgLite, bold: true, charSpacing: 4,
        valign: "middle", fontFace: "Calibri", margin: 0,
      });
      c.items.forEach((it, i) => {
        const iy = 2.45 + i * 1.13;
        s.addShape("ellipse", {
          x: c.x + 0.25, y: iy, w: 0.4, h: 0.4,
          fill: { color: c.color }, line: { width: 0 },
        });
        s.addText(String(i + 1), {
          x: c.x + 0.25, y: iy, w: 0.4, h: 0.4,
          fontSize: 13, color: C.bgLite, bold: true,
          align: "center", valign: "middle", fontFace: "Calibri", margin: 0,
        });
        s.addText(it.l, {
          x: c.x + 0.8, y: iy - 0.05, w: 5.0, h: 0.4,
          fontSize: 13, color: C.navy, bold: true, fontFace: "Calibri", margin: 0,
        });
        s.addText(it.d, {
          x: c.x + 0.8, y: iy + 0.32, w: 5.0, h: 0.7,
          fontSize: 10, color: C.textMuted, fontFace: "Calibri", margin: 0,
        });
      });
    });
  }

  // ════════════════════════════════════════════════════════════════════
  // SLIDE 20 — Closing
  // ════════════════════════════════════════════════════════════════════
  {
    const s = pres.addSlide();
    s.background = { color: C.navy };
    s.addShape("rect", { x: 0, y: 0, w: 13.333, h: 0.12,
      fill: { color: C.blue }, line: { width: 0 } });

    // Watermark
    s.addText("कवच", {
      x: 6.5, y: 0.4, w: 6.5, h: 4.5,
      fontSize: 350, color: C.blueDeep, transparency: 70,
      fontFace: "Georgia", align: "center", valign: "middle", margin: 0,
    });

    s.addText("THE SINGLE SENTENCE", {
      x: 0.7, y: 1.5, w: 12, h: 0.4,
      fontSize: 11, color: C.blueLite, bold: true, charSpacing: 6,
      fontFace: "Calibri", margin: 0,
    });

    s.addText("Fix the OpenClaw bugs so before_tool_call actually fires —",
      { x: 0.7, y: 2.1, w: 12, h: 1.2,
        fontSize: 36, color: C.bgLite, bold: true, fontFace: "Georgia", margin: 0 });
    s.addText("because until that's done, Kavach is a monitor, not a guardrail,",
      { x: 0.7, y: 3.55, w: 12, h: 0.7,
        fontSize: 24, color: C.blueLite, italic: true, fontFace: "Georgia", margin: 0 });
    s.addText("and everything else is decoration.",
      { x: 0.7, y: 4.25, w: 12, h: 0.7,
        fontSize: 24, color: C.blueLite, italic: true, fontFace: "Georgia", margin: 0 });

    // Bottom rule
    s.addShape("rect", {
      x: 0.7, y: 5.25, w: 1.0, h: 0.04,
      fill: { color: C.blue }, line: { width: 0 },
    });

    s.addText([
      { text: "Everything after that — benchmarks, new ministers, the paper — ",
        options: { color: C.blueLite, fontSize: 14 } },
      { text: "follows naturally once interception is real.",
        options: { color: C.bgLite, fontSize: 14, bold: true } },
    ], { x: 0.7, y: 5.45, w: 12, h: 0.5, fontFace: "Calibri", margin: 0 });

    // Footer
    s.addShape("rect", { x: 0, y: 7.05, w: 13.333, h: 0.45,
      fill: { color: C.blueDeep }, line: { width: 0 } });
    s.addText([
      { text: "Kavach v2  ·  ", options: { color: C.bgLite, bold: true, fontSize: 11 } },
      { text: "Capstone Progress Review  ·  May 2026  ·  ", options: { color: C.blueLite, fontSize: 11 } },
      { text: "PES University · PW26_RB_03",     options: { color: C.bgLite, fontSize: 11 } },
    ], { x: 0.5, y: 7.05, w: 12.3, h: 0.45,
        align: "center", valign: "middle", fontFace: "Calibri", margin: 0 });
  }

  // ────────────────────────────────────────────────────────────────────
  await pres.writeFile({ fileName: "/home/claude/deck/Kavach_v2_Progress_Review.pptx" });
  console.log("Deck written: /home/claude/deck/Kavach_v2_Progress_Review.pptx");
}

build().catch((err) => {
  console.error("Build failed:", err);
  process.exit(1);
});
