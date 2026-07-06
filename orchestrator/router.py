"""
Agent Router — maps agent IDs to classes and provides
lookup helpers for the API and UI layers.
"""

from agents.agent_01_intake.agent       import IntakeAgent
from agents.agent_02_analysis.agent     import AnalysisAgent
from agents.agent_03_architecture.agent import ArchitectureAgent
from agents.agent_04_security.agent     import SecurityAgent
from agents.agent_05_codegen.agent      import CodeGenAgent
from agents.agent_06_documentation.agent import DocumentationAgent
from agents.agent_07_qa.agent           import QAAgent
from agents.agent_08_review.agent       import ReviewAgent
from agents.agent_09_deployment.agent   import DeploymentAgent
from agents.agent_10_monitoring.agent   import MonitoringAgent
from agents.agent_11_support.agent      import SupportAgent

AGENT_REGISTRY: dict = {
    "agent_01_intake":       IntakeAgent,
    "agent_02_analysis":     AnalysisAgent,
    "agent_03_architecture": ArchitectureAgent,
    "agent_04_security":     SecurityAgent,
    "agent_05_codegen":      CodeGenAgent,
    "agent_06_documentation": DocumentationAgent,
    "agent_07_qa":           QAAgent,
    "agent_08_review":       ReviewAgent,
    "agent_09_deployment":   DeploymentAgent,
    "agent_10_monitoring":   MonitoringAgent,
    "agent_11_support":      SupportAgent,
}


def get_agent(agent_id: str):
    cls = AGENT_REGISTRY.get(agent_id)
    if not cls:
        raise ValueError(f"Unknown agent_id: {agent_id}")
    return cls()


def list_agents() -> list[dict]:
    return [
        {"agent_id": aid, "name": cls().name, "description": cls().description}
        for aid, cls in AGENT_REGISTRY.items()
    ]
