import papertrail

from django.http import HttpResponse
from django.utils import timezone


def index(request):
    papertrail.log(
        'hello-world',
        'Hi!',
        targets={
            'user': request.user if request.user.is_authenticated else None,
        },
        data={
            'now': timezone.now(),
        },
    )
    return HttpResponse("Hello, world.")
