import 'package:flutter/material.dart';
import 'models.dart';
import 'services.dart';

void main() {
  runApp(const TournamentApp());
}

class TournamentApp extends StatelessWidget {
  const TournamentApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Tournament',
      theme: ThemeData(useMaterial3: true),
      routes: {
        '/': (_) => const HomePage(),
        '/competitions': (_) => const CompetitionsPage(),
      },
      onGenerateRoute: (settings) {
        if (settings.name == SeasonPage.routeName) {
          final event = settings.arguments as Event;
          return MaterialPageRoute(builder: (_) => SeasonPage(event: event));
        }
        if (settings.name == DivisionPage.routeName) {
          final season = settings.arguments as Season;
          return MaterialPageRoute(builder: (_) => DivisionPage(season: season));
        }
        if (settings.name == FixturesPage.routeName) {
          final division = settings.arguments as Division;
          return MaterialPageRoute(builder: (_) => FixturesPage(division: division));
        }
        return null;
      },
    );
  }
}

class HomePage extends StatelessWidget {
  const HomePage({super.key});

  @override
  Widget build(BuildContext context) {
    final api = ApiService();
    return Scaffold(
      appBar: AppBar(
        title: const Text('News'),
        actions: [
          IconButton(
            icon: const Icon(Icons.emoji_events),
            onPressed: () => Navigator.pushNamed(context, '/competitions'),
          ),
        ],
      ),
      body: FutureBuilder<List<NewsItem>>(
        future: api.fetchNews(),
        builder: (context, snapshot) {
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final news = snapshot.data!;
          return ListView.builder(
            itemCount: news.length,
            itemBuilder: (context, index) {
              final item = news[index];
              return ListTile(title: Text(item.title), subtitle: Text(item.body));
            },
          );
        },
      ),
    );
  }
}

class CompetitionsPage extends StatelessWidget {
  const CompetitionsPage({super.key});

  @override
  Widget build(BuildContext context) {
    final api = ApiService();
    return Scaffold(
      appBar: AppBar(title: const Text('Competitions')),
      body: FutureBuilder<List<Event>>(
        future: api.fetchEvents(),
        builder: (context, snapshot) {
          if (!snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final events = snapshot.data!;
          return GridView.count(
            crossAxisCount: 2,
            children: [
              for (final e in events)
                GestureDetector(
                  onTap: () {
                    if (e.seasons.length > 1) {
                      Navigator.pushNamed(context, SeasonPage.routeName, arguments: e);
                    } else {
                      Navigator.pushNamed(context, DivisionPage.routeName, arguments: e.seasons.first);
                    }
                  },
                  child: Card(child: Center(child: Text(e.name))),
                ),
            ],
          );
        },
      ),
    );
  }
}

class SeasonPage extends StatelessWidget {
  static const routeName = '/season';
  final Event event;
  const SeasonPage({super.key, required this.event});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(event.name)),
      body: ListView(
        children: [
          for (final season in event.seasons)
            ListTile(
              title: Text(season.year.toString()),
              onTap: () => Navigator.pushNamed(context, DivisionPage.routeName, arguments: season),
            ),
        ],
      ),
    );
  }
}

class DivisionPage extends StatelessWidget {
  static const routeName = '/division';
  final Season season;
  const DivisionPage({super.key, required this.season});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text('Divisions ${season.year}')),
      body: ListView(
        children: [
          for (final d in season.divisions)
            ListTile(
              title: Text(d.name),
              onTap: () => Navigator.pushNamed(context, FixturesPage.routeName, arguments: d),
            ),
        ],
      ),
    );
  }
}

class FixturesPage extends StatelessWidget {
  static const routeName = '/fixtures';
  final Division division;
  const FixturesPage({super.key, required this.division});

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 2,
      child: Scaffold(
        appBar: AppBar(
          title: Text(division.name),
          bottom: const TabBar(tabs: [Tab(text: 'Fixtures'), Tab(text: 'Ladder')]),
        ),
        body: TabBarView(
          children: [
            _FixturesList(fixtures: division.fixtures),
            _LadderView(entries: division.ladder),
          ],
        ),
      ),
    );
  }
}

class _FixturesList extends StatelessWidget {
  final List<Fixture> fixtures;
  const _FixturesList({required this.fixtures});

  @override
  Widget build(BuildContext context) {
    return ListView(
      children: [
        for (final f in fixtures)
          ListTile(
            title: Text('${f.teamA} vs ${f.teamB}'),
            subtitle: Text('${f.time} - ${f.field}'),
            trailing: Text(f.result ?? ''),
          ),
      ],
    );
  }
}

class _LadderView extends StatelessWidget {
  final List<LadderEntry> entries;
  const _LadderView({required this.entries});

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: DataTable(
        columns: const [
          DataColumn(label: Text('Team')),
          DataColumn(label: Text('P')),
          DataColumn(label: Text('W')),
          DataColumn(label: Text('D')),
          DataColumn(label: Text('L')),
          DataColumn(label: Text('Pts')),
          DataColumn(label: Text('GD')),
        ],
        rows: [
          for (final e in entries)
            DataRow(cells: [
              DataCell(Text(e.team)),
              DataCell(Text(e.played.toString())),
              DataCell(Text(e.wins.toString())),
              DataCell(Text(e.draws.toString())),
              DataCell(Text(e.losses.toString())),
              DataCell(Text(e.points.toString())),
              DataCell(Text(e.goalDiff.toString())),
            ])
        ],
      ),
    );
  }
}
