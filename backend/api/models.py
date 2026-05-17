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
    matric_number = models.CharField(max_length=50, unique=True, auto_created=True)
    department = models.CharField(max_length=100)
    level = models.CharField(max_length=20)
    #profile_image = models.ImageField(upload_to='profile_images/', blank=True, null=True) # to be changed later to azure blob storage
    
    def __str__(self):
        return self.user.username + ' - ' + self.matric_number
    
class InstructorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    staff_id = models.CharField(max_length=50, unique=True, auto_created=True)
    department = models.CharField(max_length=100)
    specialization = models.CharField(max_length=100)

    def __str__(self):
        return self.user.username
    
class Course(models.Model):
    instructor = models.ForeignKey(InstructorProfile, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    course_code = models.CharField(max_length=20, unique=True)
    description = models.TextField()

    def __str__(self):
        return self.title
    

class Enrollment(models.Model):
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    enrollment_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('student', 'course')

class Assignment(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    description = models.TextField()
    file_url = models.TextField()
    file_type = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    due_date = models.DateTimeField()

class Materials(models.Model):
    course = models.ForeignKey(Course, on_delete=models.CASCADE)
    uploaded_by = models.ForeignKey(InstructorProfile, on_delete=models.CASCADE)
    title = models.CharField(max_length=255)
    file_url = models.TextField()
    file_type = models.CharField(max_length=50)
    upload_date = models.DateTimeField(auto_now_add=True)

class Submission(models.Model):
    assignment = models.ForeignKey(Assignment, on_delete=models.CASCADE)
    student = models.ForeignKey(StudentProfile, on_delete=models.CASCADE)
    file_url = models.TextField()
    submission_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('assignment', 'student')


class Scores(models.Model):
    submission = models.OneToOneField(Submission, on_delete=models.CASCADE)
    graded_by = models.ForeignKey(InstructorProfile, on_delete=models.SET_NULL, null=True)
    score = models.DecimalField(max_digits=5, decimal_places=2)
    feedback = models.TextField()