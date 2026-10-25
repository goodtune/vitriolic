# Translations

Each app keeps its catalogues in its own `locale/` directory:
`touchtechnology/admin`, `touchtechnology/common`, `touchtechnology/content`,
`touchtechnology/news` and `tournamentcontrol/competition`. Each one has `de`,
`fr` and `ja`.

A new locale directory has the name of the locale (for example `pt_BR`), not
the language code (`pt-br`). Django looks for that name when it loads a
catalogue, and `makemessages` refuses any other name.

## Update the catalogues

Run `makemessages` from inside each app directory, so that it reads only that
app and writes only that app's `locale/`. Use the `django-admin` of the `tox`
environment and the settings of the test project:

```sh
cd touchtechnology/common    # then each of the other four apps
DJANGO_SETTINGS_MODULE=vitriolic.settings PYTHONPATH=<repo>/tests \
    <repo>/.tox/dj61-py314/bin/django-admin makemessages -a -i tests -i migrations
```

- `-a` updates the catalogue of each language that has a directory.
- `-i tests -i migrations` skips the `tests/` and `migrations/` directories.
  A pattern with no `/` matches a directory of that name at any depth.
- Keep the default `--add-location=full`, so that each entry gives the file
  and the line that it comes from.
- Keep the obsolete entries (do not add `--no-obsolete`). They hold old
  translations that a translator can use again.

You need GNU gettext (`xgettext`, `msgmerge`, `msgfmt`), and the `tox`
environment must exist (run `tox -e dj61-py314` one time first).

Then check each catalogue:

```sh
msgfmt --check -o /dev/null <app>/locale/<locale>/LC_MESSAGES/django.po
```

`makemessages` keeps the translations that exist. When a msgid changes,
`msgmerge` can copy the old translation to the new msgid and mark it `fuzzy`.
Django does not use a fuzzy entry. A translator must examine it and remove the
mark.

The header of each catalogue gives `Project-Id-Version: vitriolic`, the
language and its plural rule. `makemessages` keeps these fields. It copies
`POT-Creation-Date` and `Report-Msgid-Bugs-To` from the template that it
makes, so leave `Report-Msgid-Bugs-To` empty. Report a problem with a
translation at <https://github.com/goodtune/vitriolic/issues>.

Do not run `compilemessages` as part of this work. A decision to compile the
`.mo` files is a separate change (see issue #449).
