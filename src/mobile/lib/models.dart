class NewsItem {
  final String title;
  final String body;
  NewsItem({required this.title, required this.body});
}

class Event {
  final String name;
  final String logo;
  final List<Season> seasons;
  Event({required this.name, required this.logo, required this.seasons});
}

class Season {
  final int year;
  final List<Division> divisions;
  Season({required this.year, required this.divisions});
}

class Division {
  final String name;
  final List<Fixture> fixtures;
  final List<LadderEntry> ladder;
  Division({required this.name, required this.fixtures, required this.ladder});
}

class Fixture {
  final String teamA;
  final String teamB;
  final String time;
  final String field;
  final String? result;
  Fixture({required this.teamA, required this.teamB, required this.time, required this.field, this.result});
}

class LadderEntry {
  final String team;
  final int played;
  final int wins;
  final int draws;
  final int losses;
  final int points;
  final int goalDiff;
  LadderEntry({required this.team, required this.played, required this.wins, required this.draws, required this.losses, required this.points, required this.goalDiff});
}
