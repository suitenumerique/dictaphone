"""
Core application factories
"""

from io import BytesIO

from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.files.storage import default_storage

import factory.fuzzy
from faker import Faker

from core import models

fake = Faker()


class UserFactory(factory.django.DjangoModelFactory):
    """A factory to random users for testing purposes."""

    class Meta:
        model = models.User

    sub = factory.Sequence(lambda n: f"user{n!s}")
    email = factory.Faker("email")
    full_name = factory.Faker("name")
    short_name = factory.Faker("first_name")
    language = factory.fuzzy.FuzzyChoice([lang[0] for lang in settings.LANGUAGES])
    password = make_password("password")


class FileFactory(factory.django.DjangoModelFactory):
    """A factory to create files"""

    class Meta:
        model = models.File
        skip_postgeneration_save = True

    title = factory.Sequence(lambda n: f"file{n}")
    creator = factory.SubFactory(UserFactory)
    deleted_at = None
    type = factory.fuzzy.FuzzyChoice([t[0] for t in models.FileTypeChoices.choices])
    filename = factory.lazy_attribute(lambda o: fake.file_name())
    upload_state = None
    size = None

    @factory.post_generation
    def update_upload_state(self, create, extracted, **kwargs):
        """Change the upload state of a file."""
        if create and extracted:
            self.upload_state = extracted
            self.save()

    @factory.post_generation
    def upload_bytes(self, create, extracted, **kwargs):
        """Save content of the file into the storage"""
        if create and extracted is not None:
            content = (
                extracted
                if isinstance(extracted, bytes)
                else str(extracted).encode("utf-8")
            )

            self.filename = kwargs.get("filename", self.filename or "content.txt")
            self.size = len(content)
            self.save()

            default_storage.save(self.file_key, BytesIO(content))
