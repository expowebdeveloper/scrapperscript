from django.shortcuts import render, redirect, reverse
from django.views import View
import os
import json
from typing import Optional
from django.http import HttpResponseRedirect, HttpResponse, Http404
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login, logout
from core_app.utils import is_valid_url, scrape_data_to_csv, scrape_inventory, scrape_price, connect_ftp, ftp_upload_file, disconnect_ftp, get_relative_path
from core_app.models import VendorSource, FtpDetail, VendorSourceFile
from django.conf import settings
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger


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
        username: Optional[str] = request.POST.get("username")
        password: Optional[str] = request.POST.get("password")
        price_xpath: Optional[str] = request.POST.get("price")
        inventory_xpath: Optional[str] = request.POST.get("inventory")

        result = is_valid_url(website)
        if result:
            
            tree_object, domain_name = scrape_data_to_csv(website)
            xpath_data = {}

            # Add price_xpath to the dictionary if it's provided
            if price_xpath:
                xpath_data['price'] = price_xpath
                #scrape data for Price
                price_inventory_result = scrape_price(tree_object, domain_name, website, price_xpath)

            # Add inventory_xpath to the dictionary if it's provided
            if inventory_xpath:
                xpath_data['inventory'] = inventory_xpath
                #scrape data for Inventory
                inventory_file_result = scrape_inventory(tree_object, domain_name, website, inventory_xpath)

            # Convert the dictionary to JSON format
            xpath_json = json.dumps(xpath_data)
            if inventory_file_result[0] and price_inventory_result[0]:
                vendor = VendorSource.objects.create(
                    website = website,
                    username = username,
                    password = password,
                    xpath  = xpath_json
                )
                vendor_file = VendorSourceFile.objects.create(
                    vendor = vendor,
                    inventory_document = inventory_file_result[1],
                    price_document = price_inventory_result[1]
                )
                ftp_detail =  FtpDetail.objects.all().last()
                if ftp_detail:
                    try:
                        ftp_server = connect_ftp(ftp_detail.host, ftp_detail.username, ftp_detail.password)
                    except Exception as e:
                        message = "Not able to connect to FTP Server"
                        return render(request, self.template_name, context={"message":message})
                    else: 
                        try:
                            inventory_relative_path = get_relative_path(vendor_file.inventory_document, settings.MEDIA_ROOT)
                            price_relative_path = get_relative_path(vendor_file.price_document, settings.MEDIA_ROOT)

                            ftp_upload_file(ftp_server, inventory_relative_path)
                            ftp_upload_file(ftp_server, price_relative_path)
                        except Exception as e:
                            
                            return render(request, self.template_name, context={"message":str(e)})
                        finally:
                            disconnect_ftp(ftp_server)
                else:
                    message = "No FTP Detail Found"
                    return render(request, self.template_name, context={"message":message})
            else:
                message = "Invalid Xpaths"
                return render(request, self.template_name, context={"message":message})
            return HttpResponseRedirect(reverse("dashboard"))
        else:
            message = "Enter Valid Website Link"
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
            website: Optional[str] = request.POST.get("website")
            username: Optional[str] = request.POST.get("username")
            password: Optional[str] = request.POST.get("password")
            price_xpath: Optional[str] = request.POST.get("price")
            inventory_xpath: Optional[str] = request.POST.get("inventory")


            result = is_valid_url(website)
            if result:
                # Convert the dictionary to JSON format
                document_detail.website = website
                document_detail.username = username
                document_detail.password = password
                xpath_data = {}
                if price_xpath:
                    xpath_data['price'] = price_xpath
                if inventory_xpath:
                    xpath_data['inventory'] = inventory_xpath
                
                # Convert the dictionary to JSON format and update the xpath field
                document_detail.xpath = json.dumps(xpath_data)

                # Save the updated VendorSource instance
                document_detail.save()

            else:
                return render(request, self.template_name, context = {"message":"Invalid Website Link", "document_detail":document_detail})
            
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
        interval: Optional[int] = request.POST.get('interval')


        if ftps.exists():
            ftp = ftps.last()

            ftp.username = username
            ftp.password = password
            ftp.host = host
            ftp.interval = interval
            ftp.save()
        else:
            try:
                ftp = FtpDetail.objects.create(
                    username=username,
                    password=password,
                    host=host,
                    port=port,
                    interval = interval
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



