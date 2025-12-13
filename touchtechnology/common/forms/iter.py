import os.path


class TemplateChoiceIterator(object):
    def __init__(self, field):
        self.field = field

    def __iter__(self):
        # Evaluate SimpleLazyObjects once at start to prevent changes during iteration
        template_base = str(self.field.template_base)
        template_folder = str(self.field.template_folder)
        folder = os.path.join(template_base, template_folder)
        choices = []
        if self.field.recursive:
            for root, dirs, files in os.walk(folder):
                for f in files:
                    if self.field.match is None or self.field.match_re.search(f):
                        f = os.path.join(root, f)
                        base = f.replace(template_base, "")
                        choices.append((base, f.replace(folder, "", 1)))
        else:
            try:
                for f in os.listdir(folder):
                    full_file = os.path.join(folder, f)
                    if os.path.isfile(full_file) and (
                        self.field.match is None or self.field.match_re.search(f)
                    ):
                        choices.append((full_file, f))
            except OSError:
                pass

        if not self.field.required:
            yield ("", self.field.empty_label)

        if choices:
            yield ("Static template", choices)

    def choice(self, obj):
        path = obj.path.replace(str(self.field.template_folder), "", 1)
        return (obj.path, "%s (%s)" % (path, obj.name))
