# Writing style

The project's Markdown is checked by [Vale](https://vale.sh), so a page reads the same whoever (or whatever) wrote it.
Run it before you open a pull request:

```bash
tox -e vale
```

Give it paths to check only those: `tox -e vale -- docs/compops.md`.
The same environment runs in CI, and an error fails the build.
Warnings and suggestions are reported but do not fail.
To see the suggestions too, run `.tox/vale/bin/vale --minAlertLevel=suggestion docs` after the first run.

Vale also has plugins for most editors, which read the same `.vale.ini`.

## Layout

- Start each sentence on a new line, and leave a blank line between paragraphs.
  A change to one sentence is then a change to one line, and a review shows what changed.
  Markdown joins the lines of a paragraph, so the rendered page is the same.
- Do not wrap a sentence over lines, and do not end a line with two spaces to force a break.
- These layout rules are for the Markdown files in the repository.
  GitHub shows each line break in a pull request description, issue or comment as a break, so there keep each paragraph on one line.
  The rules under "Words" apply there too.
- Write headings in sentence case: "Running the tests", not "Running The Tests".
  Names keep their capitals.

Vale cannot see a line break before bold or italic text, so a line that starts with `**` straight after a sentence is reported as two sentences on one line.
Start a new paragraph or list item there instead.

## Words

- Write Australian English: "colour", "organisation", "enrolment".
  There is no comma before the "and" of a list, punctuation goes outside quotation marks unless it is part of the quote, and dates are day, month, year.
- Write "for example" and "that is", not "e.g." and "i.e.".
- Write names as their owners do.
  `.vale/styles/config/vocabularies/Vitriolic/accept.txt` lists the names and terms Vale accepts, with their capitals.
  Add a word there when Vale reports a real word as a spelling mistake.

<!-- vale Vitriolic.Plain = NO -->
<!-- vale Vitriolic.Filler = NO -->

- Use the plain word: "use", not "utilise" or "leverage"; "to", not "in order to".
- Leave out words that say little, such as "comprehensive", "robust" and "seamless".
  Say what the thing does instead.

<!-- vale Vitriolic.Plain = YES -->
<!-- vale Vitriolic.Filler = YES -->

## The rules

`.vale.ini` takes Vale's own rules and the [Google developer documentation style guide](https://developers.google.com/style), less the rules that are American English or Google's own vocabulary.
Each rule that is turned off or changed has a comment that says why.
The house rules are in `.vale/styles/Vitriolic`.
`vale sync` downloads the Google package into `.vale/styles`; it is not kept in git.

`tournamentcontrol/competition/ai/SYSTEM_PROMPT.md` is not checked: it is a prompt sent to a model, and a change to its words is a change to how the model behaves.
