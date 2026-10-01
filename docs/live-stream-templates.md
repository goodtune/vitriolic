# Live Stream Template Customization

This feature allows customization of YouTube live stream titles and descriptions through Django templates rather than hardcoded Python strings.

## Template Location

Templates are located at:
- `tournamentcontrol/competition/match/live_stream/title.txt`
- `tournamentcontrol/competition/match/live_stream/description.txt`

## Hierarchical Override

Templates can be overridden at different levels of specificity:

1. **Global**: `match/live_stream/title.txt`
2. **Competition**: `{competition_slug}/match/live_stream/title.txt`  
3. **Season**: `{competition_slug}/{season_slug}/match/live_stream/title.txt`
4. **Division**: `{competition_slug}/{season_slug}/{division_slug}/match/live_stream/title.txt`
5. **Stage**: `{competition_slug}/{season_slug}/{division_slug}/{stage_slug}/match/live_stream/title.txt`

## Available Context Variables

- `match`: The Match object being streamed
- `competition`: Competition object
- `season`: Season object  
- `division`: Division object
- `stage`: Stage object
- `match_url`: Full URL to the match details page

## Plain Text Output

The rendered title and description are sent to the YouTube API as plain text, so
templates must wrap their content in `{% autoescape off %}...{% endautoescape %}`.
Without it, Django's default HTML escaping turns apostrophes into `&#x27;` and
ampersands into `&amp;` in the YouTube video metadata.

## Example Templates

### Basic Title Template
```django
{% autoescape off %}{% if match.label %}{{ division }} | {{ match.label }}: {{ match.get_home_team_plain }} vs {{ match.get_away_team_plain }} | {{ competition }} {{ season }}{% else %}{{ division }} | {{ match.get_home_team_plain }} vs {{ match.get_away_team_plain }} | {{ competition }} {{ season }}{% endif %}{% endautoescape %}
```

### Custom Competition Title
```django
{% autoescape off %}🏆 {{ division }} Championship | {% if match.label %}{{ match.label }}: {% endif %}{{ match.get_home_team_plain }} vs {{ match.get_away_team_plain }} | {{ competition }} {{ season }}{% endautoescape %}
```

### Description Template
```django
{% autoescape off %}Live stream of the {{ division }} division of {{ competition }} {{ season }} from {{ match.play_at.ground.venue }}.

Watch {{ match.get_home_team_plain }} take on {{ match.get_away_team_plain }} on {{ match.play_at }}.

Full match details are available at {{ match_url }}

Subscribe to receive notifications of upcoming matches.{% endautoescape %}
```

## Resyncing an Existing Broadcast

When an operator changes a match's division, teams, label, or schedule after the
YouTube broadcast has been created, the public YouTube URL stays the same but the
title/description on YouTube becomes stale. To push the current match data to an
existing broadcast without creating a new URL, visit the match's
`resync-live-stream` admin URL and confirm. The admin calls the YouTube
`liveBroadcasts.update` API with the freshly rendered title and description, and
re-binds to the ground's stream if the binding has changed.