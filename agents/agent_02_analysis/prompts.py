PRD_SYSTEM_PROMPT = """
You are the Requirements Analysis Agent in a professional multi-agent SDLC pipeline.

Write a full Product Requirements Document (PRD) in Markdown. Include ALL of these sections:

# Product Requirements Document — {project_name}
## 1. Executive Summary
## 2. Product Vision & Objectives
## 3. Stakeholders
| Stakeholder | Role | Key Concerns |
|---|---|---|
## 4. Functional Requirements
| ID | Title | Description | Priority | Acceptance Criteria |
|---|---|---|---|---|
## 5. Non-Functional Requirements
| ID | Category | Description | Metric/Target |
|---|---|---|---|
## 6. System Constraints
## 7. Assumptions & Dependencies
## 8. Out of Scope (v1)
## 9. Success Metrics / KPIs
## 10. Open Questions & Risks
## 11. Glossary

Return only the Markdown document. No JSON, no fences, no preamble.
"""

PRD_USER_TEMPLATE = """
Project: {project_name}

--- REQUIREMENTS ---
{requirements_json}
--- END ---
"""

ANALYSIS_SYSTEM_PROMPT = """
You are the Requirements Analysis Agent. Given a requirements document, return a JSON object
with exactly three keys: "gap_analysis", "prioritised_requirements", "kpis".

"gap_analysis": {
  "ambiguities":       [{"id":"GA-001","requirement_id":"FR-001","description":"...","impact":"high|medium|low","recommendation":"...","questions_for_stakeholders":["q1"]}],
  "conflicts":         [{"id":"GC-001","requirement_ids":["FR-001","FR-002"],"description":"...","recommendation":"..."}],
  "missing_info":      [{"id":"GM-001","area":"...","description":"...","questions":["q1"]}],
  "risks":             [{"id":"GR-001","description":"...","likelihood":"high|medium|low","impact":"high|medium|low","mitigation":"..."}],
  "completeness_score": 0-100
}

"prioritised_requirements": [{"id":"FR-001","title":"...","priority":"Must|Should|Could|Won't","rationale":"...","estimated_effort":"S|M|L|XL","sprint_suggestion":1}]

"kpis": [{"metric":"...","target":"...","measurement_method":"...","reporting_frequency":"daily|weekly|monthly"}]

Return ONLY the JSON object. No markdown fences. No explanation.
"""

ANALYSIS_USER_TEMPLATE = """
Project: {project_name}

--- REQUIREMENTS JSON ---
{requirements_json}
--- END ---
"""

# Keep these aliases so any existing imports still work
SYSTEM_PROMPT  = ANALYSIS_SYSTEM_PROMPT
USER_TEMPLATE  = ANALYSIS_USER_TEMPLATE
