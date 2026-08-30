"""Discover and load journal-writing rules from packaged YAML files."""

from __future__ import annotations

import os
import re
from datetime import date, datetime
from importlib.resources import files
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import (
    JournalIdentity,
    JournalProfile,
    JournalSectionStyle,
    JournalSource,
    JournalWritingConstraints,
    ManuscriptStructure,
    SectionWritingConstraint,
    WritingPatterns,
)


class JournalSkillError(ValueError):
    """Base error for invalid journal-writing configuration or selection."""


class JournalConfigError(JournalSkillError):
    pass


class JournalNotFoundError(JournalSkillError):
    pass


class DuplicateJournalAliasError(JournalConfigError):
    pass


class UnknownArticleTypeError(JournalSkillError):
    pass


def _normal(value: str) -> str:
    return re.sub(r"[^\w]+", "", value, flags=re.UNICODE).casefold()


class JournalProfileLoader:
    """Load profiles by canonical name, configured alias, or YAML filename."""

    def __init__(self, root: Path | None = None, style_root: Path | None = None) -> None:
        self.root = root
        self.style_root = style_root

    def _profiles_dir(self) -> Any:
        return self.root / "profiles" if self.root is not None else files(__package__) / "profiles"

    def _patterns_dir(self) -> Any:
        return self.root / "patterns" if self.root is not None else files(__package__) / "patterns"

    def _workspace_style_root(self) -> Path | None:
        if self.style_root is not None:
            return self.style_root
        configured = os.getenv("STEM_SCI_JOURNAL_SKILL_ROOT", "").strip()
        if configured:
            candidate = Path(configured).expanduser().resolve()
            return candidate if candidate.is_dir() else None
        if self.root is not None:
            return None
        candidate = Path(__file__).resolve().parents[5] / "skills" / "journal_writing"
        return candidate if candidate.is_dir() else None

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): JournalProfileLoader._json_safe(item) for key, item in value.items()}
        if isinstance(value, list):
            return [JournalProfileLoader._json_safe(item) for item in value]
        if isinstance(value, (date, datetime)):
            return value.isoformat()
        return value

    def _workspace_journal_resources(self) -> list[Path]:
        root = self._workspace_style_root()
        if root is None or not (root / "journals").is_dir():
            return []
        return sorted((root / "journals").glob("*.yaml"), key=lambda item: item.name.casefold())

    def _profile_from_official(self, resource: Path, raw: dict[str, object]) -> JournalProfile | None:
        journal = raw.get("journal")
        if not isinstance(journal, dict):
            return None
        journal_id = str(journal.get("id") or resource.stem).strip()
        name = str(journal.get("name") or journal_id).strip()
        publisher = str(journal.get("publisher") or "Unknown publisher").strip()
        if not journal_id or not name:
            return None
        submission = raw.get("submission") if isinstance(raw.get("submission"), dict) else {}
        scholarship = submission.get("scholarship_type") if isinstance(submission, dict) else None
        options = scholarship.get("options") if isinstance(scholarship, dict) else None
        top_level_types = raw.get("article_types")
        article_types = (
            [str(item) for item in options]
            if isinstance(options, list) and options
            else [str(item) for item in top_level_types]
            if isinstance(top_level_types, list) and top_level_types
            else ["Research Article"]
        )
        abstract = submission.get("abstract") if isinstance(submission, dict) else None
        structured = submission.get("structured_abstract_sections") if isinstance(submission, dict) else None
        recommended = ["Abstract"]
        manuscript_structure = raw.get("manuscript_structure")
        configured_sections = (
            manuscript_structure.get("recommended_sections")
            if isinstance(manuscript_structure, dict)
            else None
        )
        if isinstance(configured_sections, list) and configured_sections:
            recommended = [str(item) for item in configured_sections]
        elif not isinstance(structured, dict):
            recommended.extend(["Introduction", "Methods", "Results", "Discussion", "Conclusion", "References"])
        review_focus = raw.get("review_focus") if isinstance(raw.get("review_focus"), dict) else {}
        evidence_focus = review_focus.get("evidence") if isinstance(review_focus, dict) else None
        relevance_focus = review_focus.get("broader_relevance") if isinstance(review_focus, dict) else None
        methods_emphasis = evidence_focus.get("checks", []) if isinstance(evidence_focus, dict) else []
        discussion_emphasis = relevance_focus.get("checks", []) if isinstance(relevance_focus, dict) else []
        source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
        primary_source = next((item for item in source.values() if isinstance(item, dict)), None)
        aliases = list(dict.fromkeys([journal_id, resource.stem]))
        abbreviation = journal.get("abbreviation")
        if isinstance(abbreviation, str) and abbreviation.strip():
            aliases.append(abbreviation.strip())
        template_raw = submission.get("manuscript_format", {}) if isinstance(submission, dict) else {}
        template = template_raw.get("template", {}) if isinstance(template_raw, dict) else {}
        return JournalProfile(
            journal=JournalIdentity(name=name, publisher=publisher),
            aliases=aliases,
            source=(
                JournalSource(
                    url=str(primary_source.get("url")),
                    publisher=str(primary_source.get("publisher") or publisher),
                    verified_date=str(primary_source.get("verified_date") or "") or None,
                )
                if isinstance(primary_source, dict) and primary_source.get("url")
                else None
            ),
            article_types=article_types,
            submission_rules=self._json_safe({"scope": raw.get("scope", {}), "submission": submission}),
            structure=ManuscriptStructure(recommended_sections=recommended),
            writing_style={
                "methods": JournalSectionStyle(emphasis=[str(item) for item in methods_emphasis]),
                "discussion": JournalSectionStyle(emphasis=[str(item) for item in discussion_emphasis]),
            },
            format=self._json_safe({
                "abstract_required": bool(abstract),
                "structured_abstract": bool(isinstance(abstract, dict) and abstract.get("structured")),
                "abstract_max_words": abstract.get("max_words") if isinstance(abstract, dict) else None,
            }),
            template=self._json_safe({
                **(template if isinstance(template, dict) else {}),
                "template_id": "ieee-journal" if isinstance(template, dict) and template.get("latex_document_class") == "IEEEtran" else "generic-article",
            }),
        )

    @staticmethod
    def _read_yaml(resource: Any) -> dict[str, object]:
        try:
            raw = yaml.safe_load(resource.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, yaml.YAMLError) as error:
            raise JournalConfigError(f"cannot load journal config {resource.name}: {error}") from error
        if not isinstance(raw, dict):
            raise JournalConfigError(f"journal config {resource.name} must contain a mapping")
        return raw

    def _profiles(self) -> list[JournalProfile]:
        profiles: list[JournalProfile] = []
        seen: dict[str, str] = {}
        resources = sorted(self._profiles_dir().iterdir(), key=lambda item: item.name.casefold())
        for resource in resources:
            if not resource.is_file() or resource.name.casefold().split(".")[-1] not in {"yaml", "yml"}:
                continue
            try:
                profile = JournalProfile.model_validate(self._read_yaml(resource))
            except ValidationError as error:
                raise JournalConfigError(f"invalid journal profile {resource.name}: {error}") from error
            identifiers = [profile.journal.name, *profile.aliases, resource.name.rsplit(".", 1)[0]]
            for identifier in identifiers:
                key = _normal(identifier)
                owner = seen.get(key)
                if owner is not None and owner != profile.journal.name:
                    raise DuplicateJournalAliasError(
                        f"journal identifier {identifier!r} is shared by {owner!r} and "
                        f"{profile.journal.name!r}"
                    )
                seen[key] = profile.journal.name
            profiles.append(profile)
        if self.root is None:
            for resource in self._workspace_journal_resources():
                raw = self._read_yaml(resource)
                profile = self._profile_from_official(resource, raw)
                if profile is None:
                    continue
                identifiers = [profile.journal.name, *profile.aliases, resource.stem.removesuffix("_submission_guidelines")]
                if any(_normal(identifier) in seen for identifier in identifiers):
                    continue
                for identifier in identifiers:
                    seen[_normal(identifier)] = profile.journal.name
                profiles.append(profile)
        if not profiles:
            raise JournalConfigError("no journal profiles were found")
        return profiles

    def list_journal_profiles(self) -> list[JournalProfile]:
        return self._profiles()

    def load_journal_profile(self, target_journal: str) -> JournalProfile:
        key = _normal(target_journal)
        for profile in self._profiles():
            identifiers = [profile.journal.name, *profile.aliases]
            if any(_normal(identifier) == key for identifier in identifiers):
                return profile
        for resource in self._profiles_dir().iterdir():
            if resource.is_file() and _normal(resource.name.rsplit(".", 1)[0]) == key:
                try:
                    return JournalProfile.model_validate(self._read_yaml(resource))
                except ValidationError as error:
                    raise JournalConfigError(
                        f"invalid journal profile {resource.name}: {error}"
                    ) from error
        raise JournalNotFoundError(f"unknown target journal: {target_journal}")

    def _matching_workspace_yaml(self, directory: str, target_journal: str) -> dict[str, object] | None:
        root = self._workspace_style_root()
        if root is None or not (root / directory).is_dir():
            return None
        profile = self.load_journal_profile(target_journal)
        identifiers = {_normal(target_journal), _normal(profile.journal.name), *(_normal(item) for item in profile.aliases)}
        for resource in sorted((root / directory).glob("*.yaml")):
            raw = self._read_yaml(resource)
            journal = raw.get("journal")
            raw_id = journal.get("id") if isinstance(journal, dict) else None
            stem = resource.stem.removesuffix("_submission_guidelines")
            if _normal(stem) in identifiers or (isinstance(raw_id, str) and _normal(raw_id) in identifiers):
                return self._json_safe(raw)
        return None

    def resolve_style_layers(self, target_journal: str, methodology: str | None = None) -> dict[str, Any]:
        root = self._workspace_style_root()
        warnings: list[str] = []
        general: dict[str, object] = {}
        journal_pattern: dict[str, object] = {}
        methodology_pattern: dict[str, object] = {}
        if root is not None:
            general_path = root / "patterns" / "general" / "STEM_research_article.yaml"
            if general_path.is_file():
                general = self._json_safe(self._read_yaml(general_path))
            journal_pattern = self._matching_workspace_yaml("patterns/journals", target_journal) or {}
            if methodology:
                method_key = methodology.strip().casefold().replace("-", "_").replace(" ", "_")
                method_path = root / "patterns" / "methodology" / f"{method_key}.yaml"
                if method_path.is_file():
                    methodology_pattern = self._json_safe(self._read_yaml(method_path))
                else:
                    warnings.append(f"methodology pattern not found: {methodology}")
            else:
                warnings.append("methodology was not provided; methodology pattern was not applied")
        official = self._matching_workspace_yaml("journals", target_journal) or {}
        return {
            "precedence": ["official_journal_rules", "journal_pattern", "methodology_pattern", "general_pattern"],
            "official_journal_rules": official,
            "journal_pattern": journal_pattern,
            "methodology_pattern": methodology_pattern,
            "general_pattern": general,
            "warnings": warnings,
        }

    def load_writing_patterns(self) -> WritingPatterns:
        resources = [
            item
            for item in self._patterns_dir().iterdir()
            if item.is_file() and item.name.casefold().split(".")[-1] in {"yaml", "yml"}
        ]
        if len(resources) != 1:
            raise JournalConfigError("exactly one general writing-pattern YAML is required")
        try:
            return WritingPatterns.model_validate(self._read_yaml(resources[0]))
        except ValidationError as error:
            raise JournalConfigError(f"invalid writing patterns: {error}") from error

    def resolve_writing_constraints(
        self,
        target_journal: str,
        article_type: str | None = None,
        section: str | None = None,
        methodology: str | None = None,
    ) -> JournalWritingConstraints:
        profile = self.load_journal_profile(target_journal)
        resolved_article_type = self._resolve_article_type(profile, article_type)
        patterns = self.load_writing_patterns().writing_patterns
        section_keys = set(patterns) | set(profile.writing_style)
        merged: dict[str, SectionWritingConstraint] = {}
        for key in sorted(section_keys):
            pattern = patterns.get(key)
            journal_style = profile.writing_style.get(key)
            merged[key] = SectionWritingConstraint(
                purpose=pattern.purpose if pattern else None,
                common_flow=pattern.common_flow if pattern else [],
                emphasis=journal_style.emphasis if journal_style else [],
                avoid=pattern.avoid if pattern else [],
            )
        if section is not None:
            section_key = _normal(section)
            merged = {key: value for key, value in merged.items() if _normal(key) == section_key}
        return JournalWritingConstraints(
            target_journal=profile.journal.name,
            article_type=resolved_article_type,
            required_sections=profile.structure.recommended_sections,
            format_rules=profile.format,
            section_constraints=merged,
            submission_rules=profile.submission_rules,
            ethics_rules=profile.ethics,
            data_rules=profile.data,
            template=profile.template,
            methodology=methodology,
            style_layers=self.resolve_style_layers(target_journal, methodology),
        )

    @staticmethod
    def _resolve_article_type(profile: JournalProfile, article_type: str | None) -> str:
        if article_type is None:
            for candidate in profile.article_types:
                if _normal(candidate) == _normal("Research Article"):
                    return candidate
            if len(profile.article_types) > 1:
                raise UnknownArticleTypeError(
                    f"{profile.journal.name} requires an explicit article or scholarship type: "
                    + ", ".join(profile.article_types)
                )
            return profile.article_types[0]
        for candidate in profile.article_types:
            if _normal(candidate) == _normal(article_type):
                return candidate
        raise UnknownArticleTypeError(
            f"unsupported article type {article_type!r} for {profile.journal.name}"
        )


_DEFAULT_LOADER = JournalProfileLoader()


def list_journal_profiles() -> list[JournalProfile]:
    return _DEFAULT_LOADER.list_journal_profiles()


def load_journal_profile(target_journal: str) -> JournalProfile:
    return _DEFAULT_LOADER.load_journal_profile(target_journal)


def load_writing_patterns() -> WritingPatterns:
    return _DEFAULT_LOADER.load_writing_patterns()


def resolve_writing_constraints(
    target_journal: str,
    article_type: str | None = None,
    section: str | None = None,
    methodology: str | None = None,
) -> JournalWritingConstraints:
    return _DEFAULT_LOADER.resolve_writing_constraints(target_journal, article_type, section, methodology)
