from django.db import models
from django.contrib.auth.models import User

# Create your models here.
class UserProfile(models.Model):
    USER_TYPE_CHOICES = [
        ('student', 'Student'),
        ('instructor', 'Instructor'),
    ]
    
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    user_type = models.CharField(max_length=10, choices=USER_TYPE_CHOICES)
    
    def __str__(self):
        return f"{self.user.username} - {self.get_user_type_display()}"

class StudentProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    matric_number = models.CharField(max_length=50, unique=True, editable=False)
    profile_image_url = models.TextField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        if not self.matric_number:
            last_student = StudentProfile.objects.all().order_by('id').last()
            new_id = (last_student.id + 1) if last_student else 1
            self.matric_number = f"STU{new_id:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.user.username} - {self.matric_number}"
    
class InstructorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    staff_id = models.CharField(max_length=50, unique=True, editable=False)
    profile_image_url = models.TextField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.staff_id:
            last_instructor = InstructorProfile.objects.all().order_by('id').last()
            new_id = (last_instructor.id + 1) if last_instructor else 1
            self.staff_id = f"INS{new_id:05d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return self.user.username
    
class Course(models.Model):
    instructor = models.OneToOneField(InstructorProfile, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    course_code = models.CharField(max_length=20, unique=True)
    description = models.TextField()

    def __str__(self):
        return self.title
    
class Enrollment(models.Model):
    STATUS_TYPE_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    status = models.CharField(max_length=10, choices=STATUS_TYPE_CHOICES, default='pending')
    enrollment_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'course')

class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField()

class Materials(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(InstructorProfile, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField(default="")
    file_name = models.TextField(default="")
    file_url = models.TextField()
    file_type = models.CharField(max_length=100)
    upload_date = models.DateTimeField(auto_now_add=True)

class Submission(models.Model):
    SUBMISSION_STATUS_CHOICES = [
        ('submitted', 'Submitted'),
        ('graded', 'Graded')
    ]
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE)
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    file_name = models.TextField( null=True, blank=True)
    file_url = models.TextField()
    submission_date = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=10, choices=SUBMISSION_STATUS_CHOICES, default='submitted')

    class Meta:
        unique_together = ('assignment', 'student')

class Scores(models.Model):
    submission = models.OneToOneField(Submission, on_delete=models.CASCADE)
    graded_by = models.ForeignKey(InstructorProfile, on_delete=models.SET_NULL, null=True)
    score = models.DecimalField(max_digits=5, decimal_places=2)
    feedback = models.TextField()

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification for {self.user.username}"