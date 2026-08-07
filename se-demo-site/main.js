// S.A.R.A's SE Hub — interactivity
(function () {
  "use strict";

  // ---- Reveal script panel ----
  var revealBtn = document.getElementById("revealBtn");
  var codePanel = document.getElementById("codePanel");
  if (revealBtn && codePanel) {
    revealBtn.addEventListener("click", function () {
      if (codePanel.classList.contains("hidden")) {
        codePanel.classList.remove("hidden");
        revealBtn.textContent = "🛠️ Hide Script";
      } else {
        codePanel.classList.add("hidden");
        revealBtn.textContent = "⚡ Recompile & Show Script";
      }
    });
  }

  // ---- Model connection panel (mirrors Hermes `hermes setup` / `hermes model`) ----
  var form = document.getElementById("modelForm");
  if (!form) return;

  var provider = document.getElementById("provider");
  var customFields = document.getElementById("customFields");
  var infoBox = document.getElementById("infoBox");
  var infoLabel = document.getElementById("infoLabel");
  var infoDesc = document.getElementById("infoDesc");
  var infoAuth = document.getElementById("infoAuth");
  var cmdText = document.getElementById("cmdText");
  var envHint = document.getElementById("envHint");
  var baseUrl = document.getElementById("baseUrl");
  var customKey = document.getElementById("customKey");
  var customModel = document.getElementById("customModel");

  // Faithful copy of hermes_cli/models.py CANONICAL_PROVIDERS (display order),
  // grouped exactly like PROVIDER_GROUPS. Source of truth on this box.
  // auth: oauth | key | custom | special
  var GROUPS = [
    { label: "Recommended", members: [
      { id: "nous", label: "Nous Portal", desc: "Nous Portal (Everything your agent needs, 300+ models with bundled tool use)", auth: "oauth", cmd: "hermes setup --portal" },
      { id: "fireworks", label: "Fireworks AI", desc: "Fireworks AI (OpenAI-compatible direct model API)", auth: "key", env: "FIREWORKS_API_KEY", cmd: "hermes config set model.provider fireworks" },
      { id: "openrouter", label: "OpenRouter", desc: "OpenRouter (Pay-per-use API aggregator)", auth: "key", env: "OPENROUTER_API_KEY", cmd: "hermes config set model.provider openrouter" },
      { id: "moa", label: "Mixture of Agents", desc: "Mixture of Agents (named presets; aggregator acts after reference models)", auth: "special", cmd: "hermes moa configure <name>" },
      { id: "novita", label: "NovitaAI", desc: "NovitaAI (Cloud: Model API, Agent Sandbox, GPU Cloud)", auth: "key", env: "NOVITA_API_KEY", cmd: "hermes config set model.provider novita" },
      { id: "lmstudio", label: "LM Studio", desc: "LM Studio (Local desktop app with built-in model server)", auth: "custom", placeholder: "http://localhost:1234/v1" },
      { id: "anthropic", label: "Anthropic", desc: "Anthropic (Claude models via API key or Claude Code)", auth: "key", env: "ANTHROPIC_API_KEY", cmd: "hermes config set model.provider anthropic" }
    ]},
    { label: "OpenAI", members: [
      { id: "openai-codex", label: "OpenAI Codex", desc: "OpenAI Codex (Codex CLI via ChatGPT subscription or API key)", auth: "oauth", cmd: "hermes auth add openai-codex" },
      { id: "openai-api", label: "OpenAI API", desc: "OpenAI API (api.openai.com, API key)", auth: "key", env: "OPENAI_API_KEY", cmd: "hermes config set model.provider openai-api" }
    ]},
    { label: "Google Gemini", members: [
      { id: "gemini", label: "Google AI Studio", desc: "Google AI Studio (Native Gemini API)", auth: "key", env: "GOOGLE_API_KEY", cmd: "hermes config set model.provider gemini" },
      { id: "vertex", label: "Google Vertex AI", desc: "Google Vertex AI (Gemini via GCP; OAuth2 service account or ADC, GCP billing/quotas)", auth: "oauth", cmd: "hermes config set model.provider vertex" }
    ]},
    { label: "Qwen / Alibaba / Xiaomi", members: [
      { id: "alibaba", label: "Qwen Cloud", desc: "Qwen Cloud / DashScope (Qwen + multi-provider)", auth: "key", env: "DASHSCOPE_API_KEY", cmd: "hermes config set model.provider alibaba" },
      { id: "qwen-oauth", label: "Qwen OAuth (Portal)", desc: "Qwen OAuth (Reuses local Qwen CLI login)", auth: "oauth", cmd: "hermes auth add qwen-oauth" },
      { id: "xiaomi", label: "Xiaomi MiMo", desc: "Xiaomi MiMo (MiMo-V2.5 and V2 models: pro, omni, flash)", auth: "key", env: "XIAOMI_API_KEY", cmd: "hermes config set model.provider xiaomi" }
    ]},
    { label: "Kimi / Moonshot", members: [
      { id: "kimi-coding", label: "Kimi / Kimi Coding Plan", desc: "Kimi Coding Plan (api.kimi.com & Moonshot API)", auth: "key", env: "KIMI_API_KEY", cmd: "hermes config set model.provider kimi-coding" },
      { id: "kimi-coding-cn", label: "Kimi / Moonshot (China)", desc: "Kimi / Moonshot China (Domestic direct API)", auth: "key", env: "KIMI_API_KEY", cmd: "hermes config set model.provider kimi-coding-cn" }
    ]},
    { label: "MiniMax", members: [
      { id: "minimax", label: "MiniMax (Global)", desc: "MiniMax (Global direct API)", auth: "key", env: "MINIMAX_API_KEY", cmd: "hermes config set model.provider minimax" },
      { id: "minimax-oauth", label: "MiniMax (OAuth)", desc: "MiniMax via OAuth browser login (Coding Plan, minimax.io)", auth: "oauth", cmd: "hermes auth add minimax-oauth" },
      { id: "minimax-cn", label: "MiniMax (China)", desc: "MiniMax China (Domestic direct API)", auth: "key", env: "MINIMAX_CN_API_KEY", cmd: "hermes config set model.provider minimax-cn" }
    ]},
    { label: "xAI Grok", members: [
      { id: "xai", label: "xAI (Direct API)", desc: "xAI Grok (Direct API)", auth: "key", env: "XAI_API_KEY", cmd: "hermes config set model.provider xai" },
      { id: "xai-oauth", label: "xAI (SuperGrok OAuth)", desc: "xAI Grok via SuperGrok / Premium+ OAuth (no API key)", auth: "oauth", cmd: "hermes auth add xai-oauth" }
    ]},
    { label: "GitHub Copilot", members: [
      { id: "copilot", label: "GitHub Copilot", desc: "GitHub Copilot (Uses GITHUB_TOKEN or gh auth token)", auth: "key", env: "COPILOT_GITHUB_TOKEN", cmd: "hermes config set model.provider copilot" },
      { id: "copilot-acp", label: "GitHub Copilot ACP", desc: "GitHub Copilot ACP (Spawns copilot --acp --stdio)", auth: "special", cmd: "hermes config set model.provider copilot-acp" }
    ]},
    { label: "OpenCode", members: [
      { id: "opencode-zen", label: "OpenCode Zen", desc: "OpenCode Zen (Curated models, pay-as-you-go)", auth: "key", env: "OPENCODE_ZEN_API_KEY", cmd: "hermes config set model.provider opencode-zen" },
      { id: "opencode-go", label: "OpenCode Go", desc: "OpenCode Go (Open models subscription)", auth: "key", env: "OPENCODE_GO_API_KEY", cmd: "hermes config set model.provider opencode-go" }
    ]},
    { label: "Other providers", members: [
      { id: "tencent-tokenhub", label: "Tencent TokenHub", desc: "Tencent TokenHub (Hy3 Preview via tokenhub.tencentmaas.com)", auth: "key", env: "TENCENT_TOKENHUB_API_KEY", cmd: "hermes config set model.provider tencent-tokenhub" },
      { id: "nvidia", label: "NVIDIA NIM", desc: "NVIDIA NIM (Nemotron models via build.nvidia.com or local NIM)", auth: "key", env: "NVIDIA_NIM_API_KEY", cmd: "hermes config set model.provider nvidia" },
      { id: "huggingface", label: "Hugging Face", desc: "Hugging Face Inference Providers", auth: "key", env: "HF_TOKEN", cmd: "hermes config set model.provider huggingface" },
      { id: "deepseek", label: "DeepSeek", desc: "DeepSeek (V3, R1, coder, direct API)", auth: "key", env: "DEEPSEEK_API_KEY", cmd: "hermes config set model.provider deepseek" },
      { id: "zai", label: "Z.AI / GLM", desc: "Z.AI / GLM (Zhipu direct API)", auth: "key", env: "GLM_API_KEY", cmd: "hermes config set model.provider zai" },
      { id: "stepfun", label: "StepFun Step Plan", desc: "StepFun Step Plan (Agent / coding models via Step Plan API)", auth: "key", env: "STEPFUN_API_KEY", cmd: "hermes config set model.provider stepfun" },
      { id: "ollama-cloud", label: "Ollama Cloud", desc: "Ollama Cloud (Cloud-hosted open models, ollama.com)", auth: "key", env: "OLLAMA_CLOUD_API_KEY", cmd: "hermes config set model.provider ollama-cloud" },
      { id: "arcee", label: "Arcee AI", desc: "Arcee AI (Trinity models, direct API)", auth: "key", env: "ARCEE_API_KEY", cmd: "hermes config set model.provider arcee" },
      { id: "gmi", label: "GMI Cloud", desc: "GMI Cloud (Multi-model direct API)", auth: "key", env: "GMI_API_KEY", cmd: "hermes config set model.provider gmi" },
      { id: "kilocode", label: "Kilo Code", desc: "Kilo Code (Kilo Gateway API)", auth: "key", env: "KILOCODE_API_KEY", cmd: "hermes config set model.provider kilocode" },
      { id: "bedrock", label: "AWS Bedrock", desc: "AWS Bedrock (Claude, Nova, Llama, DeepSeek; IAM or API key)", auth: "key", env: "AWS_ACCESS_KEY_ID", cmd: "hermes config set model.provider bedrock" },
      { id: "azure-foundry", label: "Azure Foundry", desc: "Azure Foundry (OpenAI-style or Anthropic-style endpoint, your Azure AI deployment)", auth: "key", env: "AZURE_FOUNDry_API_KEY", cmd: "hermes config set model.provider azure-foundry" }
    ]},
    { label: "Custom endpoint", members: [
      { id: "custom", label: "Custom / Local (Ollama, your S.A.R.A model, etc.)", desc: "Custom endpoint — point Hermes at any OpenAI-compatible server (local LLM, Ollama, vLLM, your S.A.R.A model)", auth: "custom", placeholder: "https://localhost:11434/v1" }
    ]}
  ];

  // Build a flat lookup
  var BY_ID = {};
  GROUPS.forEach(function (g) {
    g.members.forEach(function (m) { BY_ID[m.id] = m; });
  });

  var AUTH_TEXT = {
    oauth: "Auth: OAuth — one login, no API key",
    key: "Auth: API key / token",
    custom: "Auth: base_url + optional key (your own / local server)",
    special: "Auth: local preset / external process"
  };

  // Populate the <select> with optgroups
  GROUPS.forEach(function (g) {
    var og = document.createElement("optgroup");
    og.label = g.label;
    g.members.forEach(function (m) {
      var opt = document.createElement("option");
      opt.value = m.id;
      opt.textContent = m.label;
      og.appendChild(opt);
    });
    provider.appendChild(og);
  });

  var STORAGE_KEY = "sara.modelSelection";

  function render() {
    var m = BY_ID[provider.value];
    if (!m) { infoBox.classList.add("hidden"); return; }

    // Toggle custom fields only for the custom endpoint
    customFields.classList.toggle("hidden", m.auth !== "custom");
    infoBox.classList.remove("hidden");

    infoLabel.textContent = m.label;
    infoDesc.textContent = m.desc;
    infoAuth.textContent = AUTH_TEXT[m.auth] || "";

    if (m.auth === "custom") {
      var url = baseUrl.value.trim() || (m.placeholder || "<base-url>");
      cmdText.textContent =
        "hermes config set model.provider custom\n" +
        "hermes config set model.base_url " + url + "\n" +
        (customModel.value.trim() ? "hermes config set model.default " + customModel.value.trim() + "\n" : "") +
        (customKey.value.trim() ? "hermes config set model.api_key <your-key>" : "# api_key optional for local servers");
      envHint.textContent = "Works with Ollama, your local S.A.R.A model (S.A.R.A-v2l), vLLM, llama.cpp — any OpenAI-compatible endpoint.";
    } else if (m.auth === "oauth") {
      cmdText.textContent = m.cmd;
      envHintNote("No key required — authenticate in the terminal/browser.");
    } else if (m.auth === "special") {
      cmdText.textContent = m.cmd;
      envHint.textContent = "Set up via its own command (no key in config.yaml for these).";
    } else {
      cmdText.textContent = m.cmd;
      envHint.textContent = "Set the env var " + m.env + " (in ~/.hermes/.env), then run the command above.";
    }
  }

  function envHintNote(text) { envHint.textContent = text; }

  provider.addEventListener("change", render);
  baseUrl.addEventListener("input", function () { if (BY_ID[provider.value].auth === "custom") render(); });
  customModel.addEventListener("input", function () { if (BY_ID[provider.value].auth === "custom") render(); });
  customKey.addEventListener("input", function () { if (BY_ID[provider.value].auth === "custom") render(); });

  // Restore any saved selection
  try {
    var saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (saved && saved.provider && BY_ID[saved.provider]) {
      provider.value = saved.provider;
      if (saved.baseUrl) baseUrl.value = saved.baseUrl;
      if (saved.customKey) customKey.value = saved.customKey;
      if (saved.customModel) customModel.value = saved.customModel;
    }
  } catch (e) {}

  form.addEventListener("submit", function (e) {
    e.preventDefault();
    var m = BY_ID[provider.value];
    var data = {
      provider: provider.value,
      baseUrl: baseUrl.value,
      customKey: customKey.value,
      customModel: customModel.value
    };
    try { localStorage.setItem(STORAGE_KEY, JSON.stringify(data)); } catch (e) {}
    envHint.textContent = "Saved '" + m.label + "' to this browser. Run the command above in a terminal to actually connect.";
  });

  document.getElementById("clearModel").addEventListener("click", function () {
    try { localStorage.removeItem(STORAGE_KEY); } catch (e) {}
    form.reset();
    render();
  });

  render();
})();
