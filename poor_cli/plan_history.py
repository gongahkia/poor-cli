"""
Plan History and Learning for poor-cli

Learn from past plans to improve future planning:
- Save plan history with outcomes
- Generate templates from successful plans
- Analytics and insights
- Auto-suggest improvements
- Pattern recognition
"""

import json
import sqlite3
from pathlib import Path
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from enum import Enum

from poor_cli.plan_mode import ExecutionPlan, PlanStep, PlanStepType, RiskLevel
from poor_cli.advanced_planning import PlanTemplate
from poor_cli.exceptions import setup_logger

logger = setup_logger(__name__)


class PlanOutcome(Enum):
    """Outcome of plan execution"""
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILURE = "failure"
    CANCELLED = "cancelled"
    ROLLBACK = "rollback"


@dataclass
class PlanExecution:
    """Record of plan execution"""
    plan_id: str
    user_request: str
    plan_summary: str
    step_count: int
    outcome: PlanOutcome
    executed_at: str
    duration_seconds: float
    steps_completed: int
    errors: List[str] = field(default_factory=list)
    plan_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "plan_id": self.plan_id,
            "user_request": self.user_request,
            "plan_summary": self.plan_summary,
            "step_count": self.step_count,
            "outcome": self.outcome.value,
            "executed_at": self.executed_at,
            "duration_seconds": self.duration_seconds,
            "steps_completed": self.steps_completed,
            "errors": self.errors,
            "plan_data": self.plan_data
        }


@dataclass
class PlanPattern:
    """Recognized pattern in plans"""
    pattern_id: str
    pattern_name: str
    description: str
    step_sequence: List[str]
    frequency: int
    success_rate: float
    avg_duration_seconds: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "pattern_id": self.pattern_id,
            "pattern_name": self.pattern_name,
            "description": self.description,
            "step_sequence": self.step_sequence,
            "frequency": self.frequency,
            "success_rate": self.success_rate,
            "avg_duration_seconds": self.avg_duration_seconds
        }


@dataclass
class PlanAnalytics:
    """Analytics from plan history"""
    total_plans: int = 0
    successful_plans: int = 0
    failed_plans: int = 0
    avg_duration_seconds: float = 0.0
    most_common_operations: List[Tuple[str, int]] = field(default_factory=list)
    success_rate_by_risk: Dict[str, float] = field(default_factory=dict)
    patterns: List[PlanPattern] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "total_plans": self.total_plans,
            "successful_plans": self.successful_plans,
            "failed_plans": self.failed_plans,
            "success_rate": self.successful_plans / self.total_plans if self.total_plans > 0 else 0.0,
            "avg_duration_seconds": self.avg_duration_seconds,
            "most_common_operations": self.most_common_operations,
            "success_rate_by_risk": self.success_rate_by_risk,
            "patterns": [p.to_dict() for p in self.patterns],
            "recommendations": self.recommendations
        }


class PlanHistoryManager:
    """Manages plan execution history"""

    def __init__(self, db_path: Optional[Path] = None):
        """Initialize plan history manager

        Args:
            db_path: Path to SQLite database (default: .poor-cli/plan_history.db)
        """
        if db_path is None:
            db_path = Path.cwd() / ".poor-cli" / "plan_history.db"

        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._init_database()

    def _init_database(self):
        """Initialize database schema"""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS plan_executions (
                    plan_id TEXT PRIMARY KEY,
                    user_request TEXT NOT NULL,
                    plan_summary TEXT,
                    step_count INTEGER,
                    outcome TEXT,
                    executed_at TEXT,
                    duration_seconds REAL,
                    steps_completed INTEGER,
                    errors TEXT,
                    plan_data TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS plan_templates (
                    template_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    steps_template TEXT,
                    created_from_plan TEXT,
                    created_at TEXT,
                    usage_count INTEGER DEFAULT 0
                )
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_outcome ON plan_executions(outcome)
            """)

            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_executed_at ON plan_executions(executed_at)
            """)

            conn.commit()

    def record_execution(self, execution: PlanExecution):
        """Record plan execution

        Args:
            execution: Plan execution record
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO plan_executions
                (plan_id, user_request, plan_summary, step_count, outcome, executed_at,
                 duration_seconds, steps_completed, errors, plan_data)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                execution.plan_id,
                execution.user_request,
                execution.plan_summary,
                execution.step_count,
                execution.outcome.value,
                execution.executed_at,
                execution.duration_seconds,
                execution.steps_completed,
                json.dumps(execution.errors),
                json.dumps(execution.plan_data)
            ))
            conn.commit()

        logger.info(f"Recorded plan execution: {execution.plan_id}")

    def get_execution(self, plan_id: str) -> Optional[PlanExecution]:
        """Get plan execution by ID

        Args:
            plan_id: Plan ID

        Returns:
            Plan execution or None
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM plan_executions WHERE plan_id = ?
            """, (plan_id,))

            row = cursor.fetchone()
            if not row:
                return None

            return self._row_to_execution(row)

    def get_recent_executions(self, limit: int = 100) -> List[PlanExecution]:
        """Get recent plan executions

        Args:
            limit: Maximum number of executions to return

        Returns:
            List of plan executions
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM plan_executions
                ORDER BY executed_at DESC
                LIMIT ?
            """, (limit,))

            return [self._row_to_execution(row) for row in cursor.fetchall()]

    def generate_analytics(
        self,
        since_days: Optional[int] = None
    ) -> PlanAnalytics:
        """Generate analytics from plan history

        Args:
            since_days: Only include plans from last N days (None = all time)

        Returns:
            Plan analytics
        """
        analytics = PlanAnalytics()

        # Build query
        query = "SELECT * FROM plan_executions"
        params = []

        if since_days:
            cutoff = (datetime.now() - timedelta(days=since_days)).isoformat()
            query += " WHERE executed_at >= ?"
            params.append(cutoff)

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)

            executions = [self._row_to_execution(row) for row in cursor.fetchall()]

        analytics.total_plans = len(executions)

        if analytics.total_plans == 0:
            return analytics

        # Calculate success rates
        outcomes = [e.outcome for e in executions]
        analytics.successful_plans = outcomes.count(PlanOutcome.SUCCESS)
        analytics.failed_plans = outcomes.count(PlanOutcome.FAILURE)

        # Calculate average duration
        durations = [e.duration_seconds for e in executions]
        analytics.avg_duration_seconds = sum(durations) / len(durations)

        # Most common operations
        all_operations = []
        for execution in executions:
            plan_data = execution.plan_data
            if 'steps' in plan_data:
                for step in plan_data['steps']:
                    all_operations.append(step.get('step_type', 'unknown'))

        operation_counts = Counter(all_operations)
        analytics.most_common_operations = operation_counts.most_common(10)

        # Success rate by risk level
        by_risk = defaultdict(lambda: {'total': 0, 'success': 0})

        for execution in executions:
            plan_data = execution.plan_data
            risk = plan_data.get('overall_risk_level', 'unknown')

            by_risk[risk]['total'] += 1
            if execution.outcome == PlanOutcome.SUCCESS:
                by_risk[risk]['success'] += 1

        analytics.success_rate_by_risk = {
            risk: (stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0.0
            for risk, stats in by_risk.items()
        }

        # Detect patterns
        analytics.patterns = self._detect_patterns(executions)

        # Generate recommendations
        analytics.recommendations = self._generate_recommendations(analytics)

        return analytics

    def save_template_from_plan(
        self,
        plan: ExecutionPlan,
        template_name: str,
        template_description: str
    ) -> PlanTemplate:
        """Save a template generated from a successful plan

        Args:
            plan: Execution plan
            template_name: Template name
            template_description: Template description

        Returns:
            Created plan template
        """
        template_id = f"learned_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # Convert plan steps to template format
        steps_template = []
        for step in plan.steps:
            step_template = {
                'step_type': step.step_type.value,
                'description': step.description,
                'tool_name': step.tool_name,
                'tool_args': step.tool_args,
                'risk_level': step.risk_level.value,
                'affected_files': step.affected_files,
                'dependencies': step.dependencies
            }
            steps_template.append(step_template)

        # Save to database
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO plan_templates
                (template_id, name, description, steps_template, created_from_plan, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                template_id,
                template_name,
                template_description,
                json.dumps(steps_template),
                plan.plan_id,
                datetime.now().isoformat()
            ))
            conn.commit()

        logger.info(f"Saved template from plan: {template_id}")

        # Create PlanTemplate object
        template = PlanTemplate(
            template_id=template_id,
            name=template_name,
            description=template_description,
            steps_template=steps_template
        )

        return template

    def get_template(self, template_id: str) -> Optional[PlanTemplate]:
        """Get saved template by ID

        Args:
            template_id: Template ID

        Returns:
            Plan template or None
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("""
                SELECT * FROM plan_templates WHERE template_id = ?
            """, (template_id,))

            row = cursor.fetchone()
            if not row:
                return None

            return PlanTemplate(
                template_id=row['template_id'],
                name=row['name'],
                description=row['description'],
                steps_template=json.loads(row['steps_template'])
            )

    def list_saved_templates(self) -> List[Tuple[str, str, str, int]]:
        """List all saved templates

        Returns:
            List of (template_id, name, description, usage_count) tuples
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT template_id, name, description, usage_count
                FROM plan_templates
                ORDER BY usage_count DESC, created_at DESC
            """)

            return cursor.fetchall()

    def increment_template_usage(self, template_id: str):
        """Increment template usage counter

        Args:
            template_id: Template ID
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                UPDATE plan_templates
                SET usage_count = usage_count + 1
                WHERE template_id = ?
            """, (template_id,))
            conn.commit()

    def suggest_improvements(self, plan: ExecutionPlan) -> List[str]:
        """Suggest improvements for a plan based on history

        Args:
            plan: Execution plan to analyze

        Returns:
            List of improvement suggestions
        """
        suggestions = []

        # Get analytics
        analytics = self.generate_analytics(since_days=90)

        if analytics.total_plans == 0:
            return suggestions

        # Check success rate by risk level
        plan_risk = plan.overall_risk_level.value
        if plan_risk in analytics.success_rate_by_risk:
            success_rate = analytics.success_rate_by_risk[plan_risk]

            if success_rate < 70.0:
                suggestions.append(
                    f"Plans with '{plan_risk}' risk level have {success_rate:.0f}% success rate. "
                    f"Consider reducing risk by breaking into smaller steps."
                )

        # Check step count
        avg_steps = sum(e.step_count for e in self.get_recent_executions(limit=50)) / 50
        if plan.get_affected_files() and len(plan.steps) > avg_steps * 1.5:
            suggestions.append(
                f"This plan has {len(plan.steps)} steps, above average ({avg_steps:.0f}). "
                f"Consider splitting into multiple smaller plans."
            )

        # Check for common patterns
        step_types = [step.step_type.value for step in plan.steps]
        for pattern in analytics.patterns:
            if pattern.success_rate > 80.0 and pattern.frequency > 5:
                # Check if this plan matches the pattern
                if self._matches_pattern(step_types, pattern.step_sequence):
                    suggestions.append(
                        f"This plan matches successful pattern '{pattern.pattern_name}' "
                        f"({pattern.success_rate:.0f}% success rate)"
                    )

        # Check for risky operations
        bash_steps = [s for s in plan.steps if s.step_type == PlanStepType.BASH_COMMAND]
        if bash_steps:
            # Check historical success rate of bash commands
            bash_executions = []
            for execution in self.get_recent_executions(limit=100):
                plan_data = execution.plan_data
                if 'steps' in plan_data:
                    has_bash = any(s.get('step_type') == 'bash' for s in plan_data['steps'])
                    if has_bash:
                        bash_executions.append(execution)

            if bash_executions:
                bash_success = sum(1 for e in bash_executions if e.outcome == PlanOutcome.SUCCESS)
                bash_rate = bash_success / len(bash_executions) * 100

                if bash_rate < 70.0:
                    suggestions.append(
                        f"Plans with bash commands have {bash_rate:.0f}% success rate. "
                        f"Verify bash commands carefully before execution."
                    )

        return suggestions

    def _row_to_execution(self, row: sqlite3.Row) -> PlanExecution:
        """Convert database row to PlanExecution"""
        return PlanExecution(
            plan_id=row['plan_id'],
            user_request=row['user_request'],
            plan_summary=row['plan_summary'],
            step_count=row['step_count'],
            outcome=PlanOutcome(row['outcome']),
            executed_at=row['executed_at'],
            duration_seconds=row['duration_seconds'],
            steps_completed=row['steps_completed'],
            errors=json.loads(row['errors']) if row['errors'] else [],
            plan_data=json.loads(row['plan_data']) if row['plan_data'] else {}
        )

    def _detect_patterns(self, executions: List[PlanExecution]) -> List[PlanPattern]:
        """Detect common patterns in successful plans"""
        patterns = []

        # Group by step sequence
        sequence_data = defaultdict(lambda: {
            'count': 0,
            'success': 0,
            'durations': []
        })

        for execution in executions:
            if 'steps' not in execution.plan_data:
                continue

            # Extract step type sequence
            sequence = tuple(s.get('step_type', 'unknown') for s in execution.plan_data['steps'])

            if len(sequence) < 2:  # Only consider sequences of 2+ steps
                continue

            sequence_data[sequence]['count'] += 1
            sequence_data[sequence]['durations'].append(execution.duration_seconds)

            if execution.outcome == PlanOutcome.SUCCESS:
                sequence_data[sequence]['success'] += 1

        # Convert to patterns
        for sequence, data in sequence_data.items():
            if data['count'] < 3:  # Must occur at least 3 times
                continue

            success_rate = (data['success'] / data['count']) * 100
            avg_duration = sum(data['durations']) / len(data['durations'])

            pattern = PlanPattern(
                pattern_id=f"pattern_{hash(sequence)}",
                pattern_name=f"{sequence[0]} → {sequence[-1]}",
                description=f"Common sequence: {' → '.join(sequence)}",
                step_sequence=list(sequence),
                frequency=data['count'],
                success_rate=success_rate,
                avg_duration_seconds=avg_duration
            )

            patterns.append(pattern)

        # Sort by frequency and success rate
        patterns.sort(key=lambda p: (p.frequency, p.success_rate), reverse=True)

        return patterns[:10]  # Top 10 patterns

    def _generate_recommendations(self, analytics: PlanAnalytics) -> List[str]:
        """Generate recommendations from analytics"""
        recommendations = []

        # Success rate recommendations
        overall_success_rate = (analytics.successful_plans / analytics.total_plans * 100) if analytics.total_plans > 0 else 0

        if overall_success_rate < 70:
            recommendations.append(
                f"Overall success rate is {overall_success_rate:.0f}%. "
                f"Consider using plan preview mode more frequently."
            )

        # Risk-based recommendations
        if 'high' in analytics.success_rate_by_risk:
            high_risk_rate = analytics.success_rate_by_risk['high']
            if high_risk_rate < 60:
                recommendations.append(
                    f"High-risk plans have {high_risk_rate:.0f}% success rate. "
                    f"Always create checkpoints before high-risk operations."
                )

        # Duration recommendations
        if analytics.avg_duration_seconds > 300:  # >5 minutes
            recommendations.append(
                f"Average plan duration is {analytics.avg_duration_seconds/60:.1f} minutes. "
                f"Consider breaking plans into smaller increments."
            )

        # Pattern-based recommendations
        if analytics.patterns:
            top_pattern = analytics.patterns[0]
            if top_pattern.success_rate > 90:
                recommendations.append(
                    f"Pattern '{top_pattern.pattern_name}' has {top_pattern.success_rate:.0f}% success rate. "
                    f"Consider creating a template from this pattern."
                )

        return recommendations

    def _matches_pattern(self, sequence: List[str], pattern: List[str]) -> bool:
        """Check if sequence matches pattern"""
        if len(sequence) != len(pattern):
            return False

        return all(s == p for s, p in zip(sequence, pattern))
