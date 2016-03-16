from django.apps import AppConfig


class PapertrailConfig(AppConfig):
    name = 'papertrail'

    def ready(self):
        import papertrail
        from papertrail import models

        for func in (
            'log',
            'related_to',
            'objects_not_represented',
            'objects_represented',
            'filter',
            'exclude',
            'all_types',
        ):
            setattr(papertrail, func, getattr(models, func))
