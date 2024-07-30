from django.urls import path
from core_app import views

urlpatterns = [
    path('', views.LoginView.as_view(), name="login"),
    path('logout', views.LogoutView.as_view(), name='logout'),
    path('dashboard', views.DasboardView.as_view(), name='dashboard'),
    path('add-detail', views.AddDetailView.as_view(), name='add-detail'),
    path('search-document', views.SearchCompanyView.as_view(), name='search-document'),

    path('delete-document/<str:id>', views.DeleteDocumentView.as_view(), name='delete-document'),
    path('edit-document/<str:id>', views.EditDocumentView.as_view(), name='edit-document'),

    path('list-ftp', views.ListFtpView.as_view(), name='list-ftp'),
    path('create-ftp/', views.CreateFtpView.as_view(), name='create-ftp'),
    path('delete-ftp/<str:id>', views.DeleteFtpView.as_view(), name='delete-ftp'),

]