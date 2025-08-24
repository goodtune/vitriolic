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

## Example Templates

### Basic Title Template
```django
{% if match.label %}{{ division }} | {{ match.label }}: {{ match.get_home_team_plain }} vs {{ match.get_away_team_plain }} | {{ competition }} {{ season }}{% else %}{{ division }} | {{ match.get_home_team_plain }} vs {{ match.get_away_team_plain }} | {{ competition }} {{ season }}{% endif %}
```

### Custom Competition Title
```django
🏆 {{ division }} Championship | {% if match.label %}{{ match.label }}: {% endif %}{{ match.get_home_team_plain }} vs {{ match.get_away_team_plain }} | {{ competition }} {{ season }}
```

### Description Template
```django
Live stream of the {{ division }} division of {{ competition }} {{ season }} from {{ match.play_at.ground.venue }}.

Watch {{ match.get_home_team_plain }} take on {{ match.get_away_team_plain }} on {{ match.play_at }}.

Full match details are available at {{ match_url }}

Subscribe to receive notifications of upcoming matches.
```