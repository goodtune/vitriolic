from __future__ import unicode_literals

import os.path


class TemplateChoiceIterator(object):
    def __init__(self, field):
        self.field = field

    def __iter__(self):
        folder = os.path.join(self.field.template_base,
                              self.field.template_folder)
        choices = []
        if self.field.recursive:
            for root, dirs, files in os.walk(folder):
                for f in files:
                    if self.field.match is None or \
                       self.field.match_re.search(f):
                        f = os.path.join(root, f)
                        base = f.replace(self.field.template_base, '')
                        choices.append((base, f.replace(folder, '', 1)))
        else:
            try:
                for f in os.listdir(folder):
                    full_file = os.path.join(folder, f)
                    if os.path.isfile(full_file) and \
                            (self.field.match is None or
                             self.field.match_re.search(f)):
                        choices.append((full_file, f))
            except OSError:
                pass

        if not self.field.required:
            yield ("", self.field.empty_label)

        if choices:
            yield ('Static template', choices)

    def choice(self, obj):
        path = obj.path.replace(self.field.template_folder, '', 1)
        return (obj.path, '%s (%s)' % (path, obj.name))
