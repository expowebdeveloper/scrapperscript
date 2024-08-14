from django.shortcuts import render, redirect, reverse
from django.views import View
import os
import json
from typing import Optional
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from core_app.utils import is_valid_url
from core_app.tasks import login_and_download_file
from core_app.models import VendorSource, FtpDetail, VendorSourceFile, VendorLogs
from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
import logging
from datetime import datetime, timedelta
logger = logging.getLogger(__name__)

class LoginView(View):
    
    template_name: str = "login.html"

    def get(self, request):
        '''
        This will get the login window.
        '''
        return render(request, self.template_name)

    def post(self, request):
        '''
        This method will using to login to the system.
        '''
        username: Optional[str] = request.POST.get("fname")
        password: Optional[str] = request.POST.get("password")
        user = authenticate(username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect("dashboard")
        message: str = "Login failed! Invalid Username and Password"
        return render(request, self.template_name, context={"message": message})


@method_decorator([login_required], name="dispatch")
class LogoutView(View):
    def get(self, request):
        '''
        This method will logout the logged in user.
        '''
        logout(request)
        return redirect("login")


@method_decorator([login_required], name="dispatch")
class DasboardView(View):
    template_name: str = "dashboard.html"

    def get(self, request):
        '''
            Get all the records to the dashboard.
        '''
        items = VendorSource.objects.all()
        paginator = Paginator(items, 10)
        page_number = request.GET.get('page', 1)
        try:
            objects = paginator.page(page_number)
        except PageNotAnInteger:
            objects = paginator.page(1)
        except EmptyPage:
            objects = paginator.page(paginator.num_pages)

        # Convert JSON xpath data to separate fields for display
        for obj in objects:
            xpath_data = json.loads(obj.xpath)
            obj.price_xpath = xpath_data.get('price', '')
            obj.inventory_xpath = xpath_data.get('inventory', '')

        return render(request, self.template_name, {"page_objects": objects})


class AddDetailView(View):
    
    template_name: str = "company.html"
    
    def get(self, request):
        
        return render(request, self.template_name)
    def post(self, request):
        '''
        This method will create new record. The method scrape_data_to_csv will get the csv file from the added link using the xpath.
        '''
        price_inventory_path = ''
        inventory_file_path= ''
        website: Optional[str] = request.POST.get("website")
        login_button_xpath: Optional[str] = request.POST.get('login')
        username_xpath: Optional[str] = request.POST.get('login_username')
        password_xpath: Optional[str] = request.POST.get('login_password')
        username: Optional[str] = request.POST.get("username")
        password: Optional[str] = request.POST.get("password")
        price_xpath: Optional[str] = request.POST.get("price")
        inventory_xpath: Optional[str] = request.POST.get("inventory")
        interval: Optional[int] = request.POST.get("interval")
        interval_unit: Optional[str] = request.POST.get("unit")
        file_url: Optional[str] = request.POST.get('file_url')
        message = ''
        result = is_valid_url(website)
        print(file_url,'=========================file_url=================')
        if file_url:
            all_url = file_url.split(',')
            print(all_url,'======================allurl====================')
            if len(all_url) > 1:
                price_url = all_url[0]
                inventory_url= all_url[1]
            else:
                price_url = all_url[0]
                inventory_url= all_url[0]
        else:
            price_url = ''
            inventory_url= ''

        if result:
            
            xpath_data = {}
            xpath_data['login_button_xpath'] = login_button_xpath if login_button_xpath else ""
            xpath_data['username_xpath'] = username_xpath if username_xpath else ""
            xpath_data['password_xpath'] = password_xpath if password_xpath else ""
            xpath_data['price'] = price_xpath
            xpath_data['inventory'] = inventory_xpath
             # Convert the dictionary to JSON format
            xpath_json = json.dumps(xpath_data)
            vendor = VendorSource.objects.filter(website=website).last()
            
            if vendor:
                if interval_unit == 'days':
                    delta = timedelta(days=vendor.interval)
                elif interval_unit == 'weeks':
                    delta = timedelta(weeks=vendor.interval)
                elif interval_unit == 'hours':
                    delta = timedelta(hours=vendor.interval)
                next_date = datetime.now() + delta
                vendor.website= website
                vendor.username = username
                vendor.password = password
                vendor.xpath = xpath_json
                vendor.unit = interval_unit
                vendor.interval = interval
                vendor.file_url = file_url
                vendor.next_due_date = next_date
                vendor.save()

            else:
                if interval:
                    if interval_unit == 'days':
                        delta = timedelta(days=int(interval))
                    elif interval_unit == 'weeks':
                        delta = timedelta(weeks=int(interval))
                    elif interval_unit == 'hours':
                        delta = timedelta(hours=int(interval))
                    next_date = datetime.now() + delta
                vendor = VendorSource.objects.create(
                        website = website,
                        username = username,
                        password = password,
                        xpath  = xpath_json,
                        interval = interval,
                        file_url = file_url,
                        unit = interval_unit,
                        next_due_date = next_date
                    )
            vendor_log = VendorLogs.objects.create(vendor=vendor)
            # Add price_xpath to the dictionary if it's provided
                
            #scrape data for Price
            try:
                if price_xpath:
                        price_inventory_result = login_and_download_file.delay(website, username, password, username_xpath, password_xpath, login_button_xpath, price_xpath, vendor.id, False, price_url)
                else:
                    price_inventory_result = login_and_download_file.delay(website, username, password, username_xpath, password_xpath, login_button_xpath, price_xpath, vendor.id, False, price_url)

            except Exception as e:
                message='Failed downloading Price data'
                vendor_log.reason = message
                vendor_log.save()


            # Add inventory_xpath to the dictionary if it's provided
            try:
                #scrape data for Inventory
                if inventory_xpath:
                        inventory_file_result = login_and_download_file.delay(website, username, password, username_xpath, password_xpath, login_button_xpath, inventory_xpath, vendor.id, True, inventory_url)
                else:
                    inventory_file_result = login_and_download_file.delay(website, username, password, username_xpath, password_xpath, login_button_xpath, inventory_xpath, vendor.id, True, inventory_url)
            except Exception as e:
                message='Failed downloading Inventory data'
                vendor_log.reason = message
                vendor_log.save()
            try:
                VendorLogs.objects.filter(file_download=False, file_upload=False, reason=None).delete()
            except:
                pass
            return HttpResponseRedirect(reverse("dashboard"))
        else:
            message = "Enter Valid Website Link"
            vendor_log.reason = message
            vendor_log.save()
        return render(request, self.template_name, context={"message":message})


@method_decorator([login_required], name="dispatch")
class DeleteDocumentView(View):
    def post(self, request, id):
        '''
        This method will delete the selected record.
        '''
        document = VendorSource.objects.get(id=id)
        document.delete()
        return HttpResponseRedirect(reverse("dashboard"))


@method_decorator([login_required], name="dispatch")
class EditDocumentView(View):
    template_name: str = "editDocument.html"

    def get(self, request, id):
        '''
        Method to get detail of edit item.
        '''
        document_detail = VendorSource.objects.get(id=id)
        xpath_data = json.loads(document_detail.xpath)
        document_detail.price = xpath_data.get('price', '')
        document_detail.inventory = xpath_data.get('inventory', '')
        document_detail.username_xpath = xpath_data.get('username_xpath', '')
        document_detail.password_xpath = xpath_data.get('password_xpath', '')
        document_detail.login_button_xpath = xpath_data.get('login_button_xpath', '')
        return render(request, self.template_name, context={"document_detail":document_detail})

    def post(self, request, id):
        '''
        This method will update the detail of the existing record.
        '''
        try:
            document_detail= VendorSource.objects.get(id=id)
            
        except VendorSource.DoesNontExist as e:
            return render(request, self.template_name, context = {"message":"Document with this Id does not exist"})
        else:
            try:
                website: Optional[str] = request.POST.get("website")
                login_button_xpath: Optional[str] = request.POST.get('login')
                username_xpath: Optional[str] = request.POST.get('login_username')
                password_xpath: Optional[str] = request.POST.get('login_password')
                username: Optional[str] = request.POST.get("username")
                password: Optional[str] = request.POST.get("password")
                price_xpath: Optional[str] = request.POST.get("price")
                inventory_xpath: Optional[str] = request.POST.get("inventory")
                interval: Optional[str] = request.POST.get("interval")
                interval_unit: Optional[str] = request.POST.get("unit")
                file_url: Optional[str] = request.POST.get("file_url")


                result = is_valid_url(website)
                if result:
                    # Convert the dictionary to JSON format
                    document_detail.website = website
                    document_detail.username = username
                    document_detail.password = password
                    document_detail.interval = interval
                    document_detail.unit = interval_unit
                    document_detail.file_url = file_url
                    xpath_data = {}
                    if price_xpath:
                        xpath_data['price'] = price_xpath
                    if inventory_xpath:
                        xpath_data['inventory'] = inventory_xpath
                    if login_button_xpath:
                        xpath_data['login_button_xpath'] = login_button_xpath
                    if username_xpath:
                        xpath_data['username_xpath'] = username_xpath
                    if password_xpath:
                        xpath_data['password_xpath'] = password_xpath
                    
                    # Convert the dictionary to JSON format and update the xpath field
                    document_detail.xpath = json.dumps(xpath_data)

                    # Save the updated VendorSource instance
                    document_detail.save()

                else:
                    return render(request, self.template_name, context = {"message":"Invalid Website Link", "document_detail":document_detail})
            except Exception as e:
                return render(request, self.template_name, context = {"message":str(e)})
        return HttpResponseRedirect(reverse("dashboard"))


@method_decorator([login_required], name="dispatch")
class DownloadDocumentView(View):
    template_name:str = "dashboard.html"
    def get(self, request, id):
        '''
        View to download document
        '''
        try:
            document = VendorSource.objects.get(id=id)
            file_path = os.path.join(settings.MEDIA_ROOT, document.document.name)
            
            if os.path.exists(file_path):
                with open(file_path, 'rb') as f:
                    response = HttpResponse(f.read(), content_type='application/octet-stream')
                    response['Content-Disposition'] = f'attachment; filename={os.path.basename(file_path)}'
                    return response
            else:
                raise Http404("File not found")
        except VendorSource.DoesNotExist:
            raise Http404("Document not found")


@method_decorator([login_required], name="dispatch")
class SearchCompanyView(View):
    template_name:str = "dashboard.html"
    
    def get(self, request):
        '''
        View to download document
        '''
        try:
            search = request.GET.get('website')
            if search:
                items = VendorSource.objects.filter(website__icontains=search)
                paginator = Paginator(items, 10)  # creating a paginator object
                # getting the desired page number from url
                page_number = request.GET.get('page', 1)
                try:
                    objects = paginator.page(page_number)
                except PageNotAnInteger:
                    # If page is not an integer, deliver the first page.
                    objects = paginator.page(1)
                except EmptyPage:
                    # If page is out of range (e.g., 9999), deliver the last page of results.
                    objects = paginator.page(paginator.num_pages)
                return render(request, self.template_name, {"page_objects":objects})
            return HttpResponseRedirect(reverse("dashboard"))
        except VendorSource.DoesNotExist:
            raise Http404("Document not found")

@method_decorator([login_required], name="dispatch")
class ListFtpView(View):
    template_name:str = "ftp.html"
    
    def get(self, request):
        '''
        View to List FTP
        '''
        ftp = FtpDetail.objects.all().last()
        
        return render(request, self.template_name, {"ftp":ftp})


@method_decorator([login_required], name="dispatch")
class CreateFtpView(View):
    template_name:str = "createFtp.html"
    
    def get(self, request):
        '''
        View to get FTP
        '''
        ftp = FtpDetail.objects.all().last()
        return render(request, self.template_name, {"ftp":ftp})

        
    def post(self, request):
        '''
        This method will update and create the detail of the  ftp record.
        '''
        ftps = FtpDetail.objects.all()
        username: Optional[str] = request.POST.get("username")
        password: Optional[str] = request.POST.get("password")
        host: Optional[str] = request.POST.get("host")
        port: Optional[int] = request.POST.get("port")


        if ftps.exists():
            ftp = ftps.last()

            ftp.username = username
            ftp.password = password
            ftp.host = host
            ftp.save()
        else:
            try:
                ftp = FtpDetail.objects.create(
                    username=username,
                    password=password,
                    host=host,
                    port=port
                )

                return HttpResponseRedirect(reverse("list-ftp"))

            except Exception as e:
                return render(request, self.template_name, context = {"message":"Something went wrong"})
        
        return HttpResponseRedirect(reverse("list-ftp"))



@method_decorator([login_required], name="dispatch")
class DeleteFtpView(View):
    def post(self, request, id):
        '''
        This method will delete the selected ftp record.
        '''
        document = FtpDetail.objects.get(id=id)
        document.delete()
        return HttpResponseRedirect(reverse("dashboard"))

@method_decorator([login_required], name="dispatch")
class DisplayLogView(View):
    template_name:str = "display_log.html"
    def get(self, request):
        items =  VendorLogs.objects.all()
        paginator = Paginator(items, 10)
        page_number = request.GET.get('page', 1)
        try:
            objects = paginator.page(page_number)
        except PageNotAnInteger:
            objects = paginator.page(1)
        except EmptyPage:
            objects = paginator.page(paginator.num_pages)

        return render(request, self.template_name, {"page_objects": objects})
    