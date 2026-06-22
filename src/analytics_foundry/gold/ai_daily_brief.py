"""Gold: business and platform product management analytics for AI Daily Brief transcripts."""

from typing import Any, Dict, List
from analytics_foundry.silver import ai_daily_brief as silver_aidb

GOLD_MBA_KEYS = (
    "record_id",
    "date",
    "title",
    "key_takeaway",
    "business_topics",
    "discussion_questions",
    "relevance_score",
)

GOLD_PM_KEYS = (
    "record_id",
    "date",
    "title",
    "platform_impact",
    "pm_domain_impact",
    "action_items",
    "pm_takeaway",
)

# Curated insights for the 11 known editions
_MBA_CURATED: Dict[str, Dict[str, Any]] = {
    "2026-06-13": {
        "key_takeaway": "The US government invoking export controls on a frontier model marks a watershed moment: AI access is now a sovereign weapon, and technology dependencies pose direct existential risks to global enterprises.",
        "business_topics": ["Sovereign AI", "Export Controls", "Balkanization of Tech", "Regulatory Capture", "CapEx & Monetization", "Fiduciary Duty"],
        "discussion_questions": [
            "How should non-US multinational corporations design their AI tech stack to insulate themselves from sudden sovereign export bans?",
            "Did Anthropic's intense marketing focus on safety and model risks inadvertently lead to its own regulatory capture and subsequent model shutdown?",
            "Evaluate the fiduciary responsibility of a board when technical dependencies can vanish overnight due to foreign government directives."
        ],
        "relevance_score": 10,
    },
    "2026-06-12": {
        "key_takeaway": "Dismantling Wall Street's token-expenditure metrics reveals a deeper truth: enterprise value comes from building workflows and agentic structures, not just burning raw tokens.",
        "business_topics": ["CAPEX", "Wall Street Valuations", "Enterprise AI Adoption", "Token Expenditure", "SpaceX IPO", "Bezos General Engineer"],
        "discussion_questions": [
            "Why is measuring raw token consumption a flawed metric for assessing AI's value creation in the enterprise?",
            "How does Bezos's investment in an 'artificial general engineer' shift the landscape of workforce planning and software development costs?",
            "Contrast the capital requirements of frontier space tech (SpaceX IPO) with frontier AI infrastructure spending."
        ],
        "relevance_score": 9,
    },
    "2026-06-11": {
        "key_takeaway": "Anthropic's attempt to silently nerf Fable 5's capabilities over safety concerns exposes the tension between vendor-aligned safety values and developer autonomy.",
        "business_topics": ["Model Alignment", "Usage Guardrails", "Data Center Infrastructure", "Resource Constraints", "Developer Backlash"],
        "discussion_questions": [
            "Should AI model providers have the right to modify or nerf deployed models post-release without developer consent?",
            "Analyze the business risk of building on proprietary models that can undergo sudden 'alignment' adjustments.",
            "How should companies evaluate the data center power revolt when planning long-term AI strategy?"
        ],
        "relevance_score": 8,
    },
    "2026-06-10": {
        "key_takeaway": "The introduction of Fable 5 and 'task imagination' shifts AI from a passive chatbot assistant to an active agent capable of planning and planning validation.",
        "business_topics": ["Model Capabilities", "Task Imagination", "Agentic Workflows", "Proprietary vs Open Weight", "Compute Subsidy"],
        "discussion_questions": [
            "What is 'task imagination' and how does it redefine the boundaries of what knowledge work can be automated?",
            "How does the shift from chatbots to agentic loops change the pricing and business models of software companies?",
            "Will the transition from the compute-subsidy era to realistic token pricing slow enterprise adoption?"
        ],
        "relevance_score": 9,
    },
    "2026-06-09": {
        "key_takeaway": "OpenAI's dual move of filing to go public and declaring its third phase signals the institutionalization of AI, while Apple's Siri integration highlights the split between consumer utility and enterprise productivity.",
        "business_topics": ["IPOs", "Public Markets", "Consumer AI vs Enterprise AI", "Apple Siri Integration", "Corporate Governance"],
        "discussion_questions": [
            "How does the corporate governance structure of OpenAI (non-profit board controlling a for-profit entity) impact its viability in public markets?",
            "Does Apple's local-first consumer AI model threaten the cloud-centric subscription business models of the frontier labs?",
            "How should enterprise IT leaders draw the line between consumer AI tools and secure enterprise-grade systems?"
        ],
        "relevance_score": 8,
    },
    "2026-06-08": {
        "key_takeaway": "The shift from simple chat interfaces to autonomous agentic loops means product managers must design systems for background execution rather than active user sessions.",
        "business_topics": ["Agentic Systems", "Workplace Productivity", "Capital Structure", "Government Equity", "Crypto Analogies"],
        "discussion_questions": [
            "What are the key differences in user experience and infrastructure load when transitioning from chat to background agents?",
            "How does the prospect of governments demanding equity in private AI labs alter the risk profile for venture capital?",
            "In what ways does the current AI buildout mirror the telecommunications infrastructure boom of the late 1990s?"
        ],
        "relevance_score": 9,
    },
    "2026-06-07": {
        "key_takeaway": "Modern work is transitioning from static documents (PDFs, PPTs) to living, interactive web links powered by AI, changing how business decisions are presented and debated.",
        "business_topics": ["Information Design", "Asset Portability", "Knowledge Management", "Collaborative Work", "Web-First Memos"],
        "discussion_questions": [
            "How does replacing a static slide deck with an interactive AI-generated link change the dynamics of a board meeting?",
            "What security and data privacy challenges arise when employees publish internal company information to shared AI pages?",
            "How should corporate training programs evolve to teach students to build interactive assets rather than slide presentations?"
        ],
        "relevance_score": 7,
    },
    "2026-06-05": {
        "key_takeaway": "Recursive self-improvement and AI nationalization are no longer science fiction; they are active planning parameters for national defense and corporate strategy.",
        "business_topics": ["Recursive Self-Improvement", "Frontier Governance", "Geopolitics", "AI Nationalization"],
        "discussion_questions": [
            "If recursive self-improvement leads to sudden capability jumps, how should a business structure its technology procurement to avoid obsolescence?",
            "What are the geopolitical implications of the US government demanding equity in AI companies?",
            "How can a general business leader evaluate the security of their data in a future of government-overseen AI labs?"
        ],
        "relevance_score": 9,
    },
    "2026-06-03": {
        "key_takeaway": "The ending of the token subsidy era forces enterprises to move past endless pilots and commit to production architectures with clear ROI.",
        "business_topics": ["Enterprise AI Implementation", "Token Subsidies", "Pilot Purgatory", "Cloud Strategy", "GSI Partnerships"],
        "discussion_questions": [
            "Why do so many enterprise AI pilots fail to reach production, and how can business leaders avoid 'pilot purgatory'?",
            "How does the transition from free/subsidized models to usage-based pricing affect the unit economics of AI SaaS products?",
            "What factors should a firm weigh when deciding between a single-cloud commitment and a multi-cloud model strategy?"
        ],
        "relevance_score": 10,
    },
    "2026-06-02": {
        "key_takeaway": "Geopolitical and market pressures are accelerating AI IPOs, raising fundamental questions about whether frontier intelligence should be governed as a private asset or a public utility.",
        "business_topics": ["IPO Readiness", "Public Goods", "Venture Capital Exits", "NVIDIA Competition", "Silicon Economics"],
        "discussion_questions": [
            "Is a public utility model viable for frontier AI development, or is private capital necessary to fund the massive compute requirements?",
            "How does hardware competition (e.g. Apple M-series vs NVIDIA RTX) impact the cost of local-first AI development?",
            "Analyze the ethical and economic trade-offs of public ownership versus private venture control of AGI development."
        ],
        "relevance_score": 8,
    },
    "2026-06-01": {
        "key_takeaway": "A shift from token abundance to a token shortage highlights the physical constraints of AI (electricity, data centers, chip supply), threatening SaaS profit margins.",
        "business_topics": ["Token Economics", "Compute Limits", "Supply Chain Constraints", "Pricing Models", "SaaS Margins"],
        "discussion_questions": [
            "How do physical constraints like electricity and chip supply chains impact the software margins of AI startups?",
            "What pricing strategies can software companies adopt to insulate their business models from rising compute costs?",
            "How should general business leaders adjust their technology budget projections in anticipation of a token shortage?"
        ],
        "relevance_score": 9,
    },
}

_PM_CURATED: Dict[str, Dict[str, Any]] = {
    "2026-06-13": {
        "platform_impact": "Downstream platform integrations (e.g. Cursor, Devin, OpenRouter) and enterprise clients using Fable 5/Mythos 5 APIs face immediate cutoff, necessitating automated model-failover routing.",
        "pm_domain_impact": "Regulatory and compliance risk management must be prioritized on the product roadmap. APIs may require KYC or ID verification processes to restrict access based on user nationality.",
        "action_items": [
            "Implement dynamic API failover to backup models (e.g., Sonnet 3.5 or GPT-4o) to prevent user workflow disruption.",
            "Audit team and customer lists for foreign-national access compliance under BIS/export controls.",
            "Begin design of KYC/identity-verification onboarding flow for API consumers."
        ],
        "pm_takeaway": "Single-model dependency is an existential threat. AI Platform PMs must build resilient, model-agnostic abstraction layers and failover systems.",
    },
    "2026-06-12": {
        "platform_impact": "Raw token consumption is a poor proxy for value. Platforms must focus on providing pre-built workflows, agent templates, and orchestration APIs rather than raw inference access.",
        "pm_domain_impact": "SaaS pricing models must shift from usage-based token markups to outcome-based or workflow-subscription models to protect gross margins.",
        "action_items": [
            "Revise platform pricing strategy to charge per successful task run rather than per thousand tokens.",
            "Develop orchestration layer features that reduce token waste through intelligent context window management.",
            "Incorporate 'agentic coworkers' into the development roadmap to capitalize on the workflow-centric demand."
        ],
        "pm_takeaway": "Platform value is in the orchestration and workflows, not the raw tokens. Build context-aware, cost-efficient agent rails.",
    },
    "2026-06-11": {
        "platform_impact": "Sudden model updates or alignment 'nerfing' by providers can break downstream application behavior, making regression testing and version locking critical.",
        "pm_domain_impact": "Service Level Agreements (SLAs) with proprietary model vendors are unreliable. PMs must plan for alternative open-weight models that can be self-hosted.",
        "action_items": [
            "Establish automatic regression and behavioral testing suites for downstream apps to detect model nerfing instantly.",
            "Incorporate open-weight model hosting (e.g., Llama, Qwen) into the platform architecture to ensure operational independence.",
            "Draft vendor SLA risk disclosures for enterprise customers."
        ],
        "pm_takeaway": "Proprietary model providers are single points of failure. Diversify with self-hosted open weight models to maintain product stability.",
    },
    "2026-06-10": {
        "platform_impact": "The transition to agentic loops and 'task imagination' requires platform APIs to support long-running, asynchronous executions and state management.",
        "pm_domain_impact": "Roadmaps must shift from simple conversational UX (chat) to canvas-based or background execution UX suitable for agentic planning.",
        "action_items": [
            "Design APIs that support stateful, multi-turn agent sessions and asynchronous execution notifications (webhooks).",
            "Create a planning validation UI that allows users to review and edit an agent's plan before execution starts.",
            "Optimize token caching and prompt engineering to support large context sizes required by task imagination."
        ],
        "pm_takeaway": "Ditch the chat box. Build stateful, asynchronous platform infrastructure to enable true background agent execution.",
    },
    "2026-06-09": {
        "platform_impact": "Apple's local-first consumer AI model pushes developers to build hybrid applications that split inference between local chips and secure cloud environments.",
        "pm_domain_impact": "The platform roadmap must support edge-computing deployment options for data privacy and latency optimization.",
        "action_items": [
            "Investigate ONNX runtime or local CoreML deployment paths for smaller, conformed models on edge devices.",
            "Build hybrid routing middleware that runs low-complexity tasks on the client device and escalates complex queries to the cloud.",
            "Establish zero-trust data ingestion boundaries for cloud model handoffs."
        ],
        "pm_takeaway": "The future is hybrid. Design platforms that optimize for latency, privacy, and cost by routing between local and cloud inference.",
    },
    "2026-06-08": {
        "platform_impact": "As AI use shifts to agents and coding loops, developers need robust SDKs, debuggers, and tracing tools to inspect agent planning steps and memory states.",
        "pm_domain_impact": "Developer platform utility (DX) is the new battleground. PMs must build APIs that expose model thinking paths and intermediate states.",
        "action_items": [
            "Integrate open tracing (e.g. Arize, LangSmith) directly into the platform's API gateway.",
            "Create a visual debugger for developer customers to step through agent execution loops and inspect memory/context.",
            "Establish strict rate-limit and cost-control guards for agentic loops to prevent runaway token bills."
        ],
        "pm_takeaway": "Agent developers need observability, not just inference. Build first-class debugging and tracing into your platform APIs.",
    },
    "2026-06-07": {
        "platform_impact": "The shift to web-first, living links requires platforms to provide hosting, real-time collaboration, and secure sharing infrastructure for AI-generated artifacts.",
        "pm_domain_impact": "Product roadmaps must include collaborative workspace features, access control (RBAC), and interactive component libraries.",
        "action_items": [
            "Build secure, fast sharing links and permission settings for all AI-generated output pages.",
            "Create interactive component APIs (charts, tables, sliders) that AI models can dynamically render in real-time.",
            "Implement real-time multiplayer editing (CRDTs) for shared AI workspaces."
        ],
        "pm_takeaway": "Don't generate text; generate applications. Provide the hosting and interactive rails to turn AI outputs into living products.",
    },
    "2026-06-05": {
        "platform_impact": "Geopolitical nationalization of AI labs means platforms must prepare for sovereign cloud requirements (e.g., EU-only data zones, US GovCloud integrations).",
        "pm_domain_impact": "Security compliance, local data residency, and auditability are critical for enterprise sales and must be prioritized on the roadmap.",
        "action_items": [
            "Establish hosting zones in multiple geographic regions (US GovCloud, EU Frankfurt) to meet nationalization compliance.",
            "Implement strict logging, audit trails, and data encryption-at-rest keys managed by the customer.",
            "Define backup failovers to European open-weight alternatives (e.g. Mixtral) for EU clients."
        ],
        "pm_takeaway": "Sovereign boundaries are returning to software. PMs must design multi-region compliance and data sovereignty into the platform core.",
    },
    "2026-06-03": {
        "platform_impact": "Enterprises need platforms that connect to legacy databases, support custom fine-tuning, and guarantee reliability through strict data quality and guardrails.",
        "pm_domain_impact": "The PM focus must shift from 'wow' factor to operational metrics: latency, reliability, integration cost, and data security.",
        "action_items": [
            "Build connectors for enterprise data systems (SQL Server, SAP, Salesforce) with automated schema mapping.",
            "Develop automated guardrail APIs that block toxic, hallucinated, or non-compliant outputs before they reach the user.",
            "Publish clear TCO (Total Cost of Ownership) calculators and ROI metrics for enterprise customers."
        ],
        "pm_takeaway": "Enterprise AI is about plumbing and safety, not just smart models. Focus on secure integrations and predictable guardrails.",
    },
    "2026-06-02": {
        "platform_impact": "Hardware diversity (Apple Silicon, local GPUs) enables local-first development platforms that operate independently of central cloud APIs.",
        "pm_domain_impact": "Open-source and local hosting reduce platform operational costs (OpEx) and mitigate vendor dependencies.",
        "action_items": [
            "Create a local developer desktop client that runs small models (e.g. Llama-3-8B) natively on local hardware.",
            "Establish local-first sync protocols that allow apps to function offline and sync back to the cloud.",
            "Draft open-source model contribution and integration guidelines for the platform community."
        ],
        "pm_takeaway": "Leverage edge hardware to reduce API billing. Build local-first options to offer developers cost-effective and private alternatives.",
    },
    "2026-06-01": {
        "platform_impact": "Supply chain constraints require platforms to implement strict traffic management, rate-limiting, and context window compression techniques.",
        "pm_domain_impact": "Gross margin management is paramount. PMs must optimize context windows and cache prompts to minimize token consumption.",
        "action_items": [
            "Implement prompt caching (e.g. Anthropic Prompt Caching) across all platform APIs to cut token costs by up to 90%.",
            "Build context compression algorithms that summarize chat history or prune redundant system instructions.",
            "Set up dynamic rate limits based on hardware availability and tier-based traffic prioritization."
        ],
        "pm_takeaway": "Tokens are a finite, expensive resource. Prioritize prompt caching, context compression, and rate-limiting to protect gross margins.",
    },
}


def get_mba_impact() -> List[Dict[str, Any]]:
    """Transform conformed silver transcripts into MBA Coursework Impact gold metrics."""
    transcripts = silver_aidb.get_cleaned_transcripts()
    out = []
    for trans in transcripts:
        date_str = trans["date"]
        curated = _MBA_CURATED.get(date_str)
        if curated:
            rec = {
                "record_id": trans["record_id"],
                "date": date_str,
                "title": trans["title"],
                "key_takeaway": curated["key_takeaway"],
                "business_topics": curated["business_topics"],
                "discussion_questions": curated["discussion_questions"],
                "relevance_score": curated["relevance_score"],
            }
        else:
            # Smart fallback for future dates
            text = trans["transcript_text"].lower()
            topics = []
            if any(k in text for k in ("chip", "nvidia", "gpu", "compute", "tsmc")):
                topics.append("Geopolitical Compute Supply Chains")
            if any(k in text for k in ("openai", "anthropic", "meta", "mistral", "google")):
                topics.append("Frontier Labs Strategy")
            if any(k in text for k in ("export", "control", "bis", "regulation", "law", "policy")):
                topics.append("Regulatory Compliance")
            if any(k in text for k in ("agent", "loop", "autonomy", "asynchronous")):
                topics.append("Agentic Architectures")
            if any(k in text for k in ("startup", "ipo", "valuation", "venture", "fund")):
                topics.append("Silicon Valley Economics")
            if not topics:
                topics = ["AI Ecosystem Trends"]

            rec = {
                "record_id": trans["record_id"],
                "date": date_str,
                "title": trans["title"],
                "key_takeaway": trans["teaser"] or "Analysis of the strategic business implications of current AI news.",
                "business_topics": topics,
                "discussion_questions": [
                    "How does the shift described in this brief affect the strategic roadmap of non-tech companies?",
                    "What are the operational risks of relying on third-party model providers versus open-source alternatives?",
                    "Assess the geopolitical or economic forces that might disrupt the technology discussed in this brief."
                ],
                "relevance_score": 8,
            }
        out.append(rec)
    return out


def get_product_strategy_impact() -> List[Dict[str, Any]]:
    """Transform conformed silver transcripts into AI Platform Product Strategy gold metrics."""
    transcripts = silver_aidb.get_cleaned_transcripts()
    out = []
    for trans in transcripts:
        date_str = trans["date"]
        curated = _PM_CURATED.get(date_str)
        if curated:
            rec = {
                "record_id": trans["record_id"],
                "date": date_str,
                "title": trans["title"],
                "platform_impact": curated["platform_impact"],
                "pm_domain_impact": curated["pm_domain_impact"],
                "action_items": curated["action_items"],
                "pm_takeaway": curated["pm_takeaway"],
            }
        else:
            # Smart fallback for future dates
            rec = {
                "record_id": trans["record_id"],
                "date": date_str,
                "title": trans["title"],
                "platform_impact": "Developers must design for high model availability, rate-limiting, and cost-efficiency when deploying these models downstream.",
                "pm_domain_impact": "AI Product Managers should plan for rising API costs and build flexible, multi-model architectures.",
                "action_items": [
                    "Audit current API usage and implement prompt caching.",
                    "Evaluate open-source alternatives to minimize vendor lock-in.",
                    "Implement automated fallback mechanisms to handle API outages."
                ],
                "pm_takeaway": "Product managers must optimize context windows and build model-agnostic gateways to manage margins and uptime.",
            }
        out.append(rec)
    return out
