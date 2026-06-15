from django.shortcuts import redirect, render

def redirect_to_login(request):
    return redirect("login_page")

def custom_401_view(request, exception):
    return render(request, '401_page.html', status=401)

def custom_403_view(request, exception):
    return render(request, '401_page.html', status=403)

def custom_404_view(request, exception):
    return render(request, '404_page.html', status=404)