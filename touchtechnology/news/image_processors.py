from django.utils.module_loading import import_string


def processor_factory(defs):
    processors = []
    for path, args, kwargs in defs:
        processor = import_string(path)
        processors.append(processor(*args, **kwargs))
    return processors
