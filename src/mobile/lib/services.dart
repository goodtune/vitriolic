import 'models.dart';

class ApiService {
  Future<List<NewsItem>> fetchNews() async {
    return [
      NewsItem(title: 'Welcome to the Tournament', body: 'Stay tuned for updates'),
      NewsItem(title: 'Finals Approaching', body: 'Big games this weekend'),
    ];
  }

  Future<List<Event>> fetchEvents() async {
    return _events;
  }
}

final _ladder = [
  LadderEntry(team: 'ThunderCats', played: 3, wins: 3, draws: 0, losses: 0, points: 9, goalDiff: 12),
  LadderEntry(team: 'StormBreakers', played: 3, wins: 2, draws: 0, losses: 1, points: 6, goalDiff: 5),
];

final _fixtures = [
  Fixture(teamA: 'ThunderCats', teamB: 'StormBreakers', time: '3:00 PM', field: 'Field 1', result: '2-1'),
  Fixture(teamA: 'Wildcats', teamB: 'Eagles', time: '4:00 PM', field: 'Field 2', result: null),
];

final _divisions = [
  Division(name: "Men's Open", fixtures: _fixtures, ladder: _ladder),
  Division(name: "Women's 40s", fixtures: _fixtures, ladder: _ladder),
];

final _events = [
  Event(name: 'Summer Cup', logo: 'assets/images/logo.png', seasons: [
    Season(year: 2024, divisions: _divisions),
    Season(year: 2025, divisions: _divisions),
  ]),
];
