import 'package:flutter_test/flutter_test.dart';
import 'package:tournament_app/main.dart';

void main() {
  testWidgets('App builds', (tester) async {
    await tester.pumpWidget(const TournamentApp());
    expect(find.text('News'), findsOneWidget);
  });
}
