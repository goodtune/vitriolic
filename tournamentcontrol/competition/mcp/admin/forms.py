"""
Forms used only by the administration MCP tools.

The admin site's match forms do not offer the fields that decide a side of a
match by formula (``home_team_eval``, ``away_team_eval`` and the match a
winner or loser reference points at). Agents repairing or hand-building
finals need them, so these subclasses add them, with validation, without
changing the forms the admin site renders.
"""

from django import forms

from tournamentcontrol.competition.forms import MatchEditForm, MatchStreamForm
from tournamentcontrol.competition.models import Match, SeasonMatchTime, Stage
from tournamentcontrol.competition.utils import stage_group_position_re

EVAL_FIELDS = (
    "home_team_eval",
    "home_team_eval_related",
    "away_team_eval",
    "away_team_eval_related",
)

WIN_LOSE = ("W", "L")


def _teams_in(node):
    """How many teams a stage or pool holds (decided or not)."""
    return max(node.teams.count(), node.undecided_teams.count())


def position_eval_error(stage, team_eval):
    """
    Why the positional eval ``team_eval`` (``P1``, ``G2P3``, ``S1G1P2``) on
    a match of ``stage`` cannot be evaluated, or ``None`` when it can: it
    must name an earlier stage (by default the one ``stage`` follows), a
    pool that exists in it, and a position within its number of teams.
    """
    syntax = stage_group_position_re.fullmatch(team_eval)
    if syntax is None:
        return (
            f"{team_eval} is not an eval: use P1 (position on the ladder of "
            "the previous stage), G2P3 (position 3 in its pool 2), S1G1P2 "
            "(stage 1, pool 1, position 2), W or L."
        )
    stage_number, group_number, position = syntax.groups()
    if "0" in (stage_number, group_number, position):
        return f"{team_eval}: stage, pool and position numbers start at 1."
    # Resolved as ``utils.stage_group_position`` resolves it when the
    # match is evaluated.
    if stage_number is None:
        try:
            ref_stage = stage.comes_after
        except Stage.DoesNotExist:
            return (
                f"{team_eval} refers to the stage before this one, but "
                f"{stage.title} is the first stage of the division."
            )
    else:
        stages = list(stage.division.stages.all())
        if int(stage_number) > len(stages):
            return f"{team_eval}: the division has no stage {stage_number}."
        ref_stage = stages[int(stage_number) - 1]
    group = None
    if group_number is not None:
        pools = list(ref_stage.pools.order_by("order"))
        if int(group_number) > len(pools):
            return (
                f"{team_eval}: {ref_stage.title} has no pool {group_number} "
                f"(it has {len(pools)})."
            )
        group = pools[int(group_number) - 1]
    position = int(position)
    if ref_stage.order >= stage.order:
        return f"{team_eval} must refer to an earlier stage than {stage.title}."
    node = group if group is not None else ref_stage
    size = _teams_in(node)
    if position > size:
        return (
            f"{team_eval} refers to position {position}, but {node.title} "
            f"has {size} team{'' if size == 1 else 's'}."
        )
    return None


class AgentMatchEvalMixin:
    """
    Offer and validate the eval fields of a match:

    * a side is given one of a team, an undecided team or an eval;
    * a positional eval (``P1``, ``G2P3``, ``S1G1P2``) must name an earlier
      stage (by default the one this stage comes after), a pool that exists
      in it, and a position no greater than the number of teams there;
    * a ``W`` or ``L`` eval needs the match it refers to, in the same
      division and either in an earlier stage or in an earlier round of
      this stage, which rules out self references and cycles.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        stage = self.instance.stage
        if stage is None:
            return
        related = Match.objects.filter(stage__division=stage.division)
        if self.instance.pk is not None:
            related = related.exclude(pk=self.instance.pk)
        for side in ("home", "away"):
            field = self.fields.get(f"{side}_team_eval_related")
            if field is not None:
                field.queryset = related
                field.error_messages["invalid_choice"] = (
                    "The related match must be another match of this division."
                )

    def clean(self):
        cleaned_data = super().clean() or self.cleaned_data
        for side in ("home", "away"):
            if {f"{side}_team_eval", f"{side}_team_eval_related"} & set(
                self.changed_data
            ):
                self._clean_eval(side, cleaned_data)
        return cleaned_data

    def _value(self, cleaned_data, name):
        if name in self.fields:
            return cleaned_data.get(name)
        return getattr(self.instance, name)

    def _clean_eval(self, side, cleaned_data):
        eval_field = f"{side}_team_eval"
        related_field = f"{side}_team_eval_related"
        team_eval = (cleaned_data.get(eval_field) or "").strip().upper() or None
        related = cleaned_data.get(related_field)
        cleaned_data[eval_field] = team_eval

        if related is not None and team_eval not in WIN_LOSE:
            self.add_error(
                related_field,
                "A related match is only used with a W (winner) or L (loser) eval.",
            )
        if team_eval is None:
            return

        if self._value(cleaned_data, f"{side}_team") or self._value(
            cleaned_data, f"{side}_team_undecided"
        ):
            self.add_error(
                eval_field,
                f"Give the {side} side one of a team, an undecided team or an "
                "eval, not more than one.",
            )
            return

        if team_eval in WIN_LOSE:
            if related_field in self.errors:
                # The related match given is not usable; that is the error.
                return
            error = self._win_lose_error(side, related, cleaned_data)
        else:
            error = self._position_error(team_eval)
        if error:
            self.add_error(eval_field, error)
        else:
            # Like a generated draw: still waiting to be evaluated.
            self.instance.evaluated = False

    def _win_lose_error(self, side, related, cleaned_data):
        if related is None:
            return (
                "A W or L eval needs the match it refers to "
                f"({side}_team_eval_related_id)."
            )
        stage = self.instance.stage
        if related.stage.order > stage.order:
            return (
                f"Match {related.pk} is in a later stage; a W or L eval must "
                "refer to an earlier match."
            )
        if related.stage_id == stage.pk:
            round = self._value(cleaned_data, "round")
            if round is None or related.round is None or related.round >= round:
                return (
                    f"Match {related.pk} is in round {related.round} of this "
                    "stage; a W or L eval must refer to a match in an earlier "
                    "stage or an earlier round of this stage"
                    + ("" if round is not None else " (give this match a round)")
                    + "."
                )
        # Belt and braces: the ordering above makes a cycle impossible, but
        # existing data may predate it.
        seen = {self.instance.pk} - {None}
        pending = [related]
        while pending:
            match = pending.pop()
            if match.pk in seen:
                return f"Match {related.pk} would make the eval references circular."
            seen.add(match.pk)
            pending.extend(
                m
                for m in (match.home_team_eval_related, match.away_team_eval_related)
                if m is not None
            )
        return None

    def _position_error(self, team_eval):
        return position_eval_error(self.instance.stage, team_eval)


class AgentMatchEditForm(AgentMatchEvalMixin, MatchEditForm):
    class Meta(MatchEditForm.Meta):
        fields = MatchEditForm.Meta.fields + EVAL_FIELDS


class AgentMatchStreamForm(AgentMatchEvalMixin, MatchStreamForm):
    class Meta(MatchStreamForm.Meta):
        fields = MatchStreamForm.Meta.fields + EVAL_FIELDS


class SeasonMatchTimeForm(forms.ModelForm):
    """
    A season time slot rule, with the fields the admin site's time slot
    form offers.
    """

    class Meta:
        model = SeasonMatchTime
        fields = ("start_date", "end_date", "start", "interval", "count")

    def clean_interval(self):
        interval = self.cleaned_data.get("interval")
        if interval is not None and interval < 1:
            raise forms.ValidationError("The interval must be at least 1 minute.")
        return interval

    def clean_count(self):
        count = self.cleaned_data.get("count")
        if count is not None and count < 1:
            raise forms.ValidationError("There must be at least 1 time slot.")
        return count

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get("start_date")
        end_date = cleaned_data.get("end_date")
        if start_date and end_date and end_date < start_date:
            self.add_error("end_date", "The rule cannot end before it starts.")
        return cleaned_data
