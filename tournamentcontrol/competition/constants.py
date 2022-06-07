import pytz
from dateutil.rrule import DAILY, WEEKLY
from django.utils.translation import gettext_lazy as _

GENDER_CHOICES = (
    ("M", _("Male")),
    ("F", _("Female")),
    ("X", _("Unspecified")),
)

SEASON_MODE_CHOICES = (
    (WEEKLY, _("Season")),
    (DAILY, _("Tournament")),
)

WIN_LOSE = {
    "W": _("Winner"),
    "L": _("Loser"),
}

##########
# RawSQL #
##########

MATCH_TIMELINE_EVENTS = """
SELECT
    m.uuid, m.timestamp, m.match_id, m.type, m.team_id, m.details
    , COUNT(DISTINCT e.timestamp) period
    , MAX(e.timestamp) period_timestamp
    , AGE(m.timestamp, MAX(e.timestamp)) relative_timestamp
    , CASE WHEN (s.home_score IS NULL) THEN 0 ELSE s.home_score END
    , CASE WHEN (s.away_score IS NULL) THEN 0 ELSE s.away_score END
FROM
    competition_matchevent m
LEFT OUTER JOIN
    competition_matchevent e
ON
    (
        e.match_id = m.match_id
        AND e.type = 'TIME'
        AND '["START","RESUME"]'::jsonb @> e.details
        AND e.timestamp <= m.timestamp
    )
LEFT OUTER JOIN
	(
		SELECT
			m.match_id, m.timestamp
			, SUM(CASE WHEN (e.details @> '{"team":"HOME"}'::jsonb AND e.type = 'SCORE') THEN ((e.details ->> 'points'))::integer ELSE 0 END) home_score
			, SUM(CASE WHEN (e.details @> '{"team":"AWAY"}'::jsonb AND e.type = 'SCORE') THEN ((e.details ->> 'points'))::integer ELSE 0 END) away_score
		FROM
			competition_matchevent m
		INNER JOIN
			competition_matchevent e
		ON
			(
				e.match_id = m.match_id
		        AND e.timestamp <= m.timestamp
		    )
		WHERE
			m.type = 'SCORE'
		GROUP BY
			m.match_id, m.timestamp
	) s
ON
	(
		s.match_id = m.match_id
        AND s.timestamp = m.timestamp
	)
WHERE
    m.type != 'TIME' AND m.match_id = %s
GROUP BY
    m.uuid, m.timestamp, m.match_id, m.type, m.team_id, m.details
    , s.home_score, s.away_score
ORDER BY
    m.timestamp DESC
"""

###################
# TIME ZONE NAMES #
###################

"""
Ideally this would be a better list for the specific uses of the site in
question. For example, it is perhaps much easier to list just the Australian
time zones for sites deployed for Australian customers.

This is also implemented in touchtechnology.common.forms and should probably
be moved and better leveraged in future release.

See https://bitbucket.org/touchtechnology/common/issue/16/
"""


PYTZ_TIME_ZONE_CHOICES = [("\x20Standard", (("UTC", "UTC"), ("GMT", "GMT")))]
for iso, name in pytz.country_names.items():
    values = sorted(pytz.country_timezones.get(iso, []))
    names = [s.rsplit("/", 1)[1].replace("_", " ") for s in values]
    PYTZ_TIME_ZONE_CHOICES.append((name, [each for each in zip(values, names)]))
PYTZ_TIME_ZONE_CHOICES.sort()
