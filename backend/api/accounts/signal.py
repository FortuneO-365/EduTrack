from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User, Group
from ..models import StudentProfile, InstructorProfile


@receiver(post_save, sender=StudentProfile)
def add_student_group(sender, instance, created, **kwargs):

    if created:

        student_group, _ = Group.objects.get_or_create(
            name='Student'
        )

        instance.user.groups.add(student_group)


@receiver(post_save, sender=InstructorProfile)
def add_instructor_group(sender, instance, created, **kwargs):

    if created:

        instructor_group, _ = Group.objects.get_or_create(
            name='Instructor'
        )

        instance.user.groups.add(instructor_group)