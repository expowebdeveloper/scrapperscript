from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import shutil
import tempfile
from lxml import html
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from requests.exceptions import RequestException
from selenium.webdriver.chrome.service import Service as ChromeService
from celery.exceptions import SoftTimeLimitExceeded
import time
import os
from tenacity import retry, wait_fixed, stop_after_attempt, retry_if_exception_type

from django.conf import settings
from datetime import datetime, timedelta
from celery import shared_task
from .utils import ensure_https, wait_for_download_complete, get_domain_name, get_relative_path, connect_ftp, disconnect_ftp, ftp_upload_file, scrape_price, scrape_inventory
from .models import VendorLogs, VendorSourceFile, FtpDetail, VendorSource
import requests


@shared_task(time_limit=333333, soft_time_limit=333333)
def login_and_download_file(login_url, username, password, username_xpath, password_xpath, login_xpath, file_download_xpath, vendor, inventory, file_download_url=""):
    try:
        vendor_source = VendorSource.objects.filter(id=vendor).last()
        vendor_log = VendorLogs.objects.create(vendor=vendor_source)
        with tempfile.TemporaryDirectory() as temp_dir:
            # Configure Chrome options
            chrome_options = Options()
            chrome_options.add_argument("--headless")  # Run in headless mode
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--disable-popup-blocking")  # Disable popup blocking

            # Set download preferences to use the temporary directory
            prefs = {
                "download.default_directory": temp_dir,
                "download.prompt_for_download": False,
                "download.directory_upgrade": True,
                "safebrowsing.enabled": True
            }
            chrome_options.add_experimental_option("prefs", prefs)

            # Initialize the WebDriver
            # driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
            # for Server Use
            path = "/usr/bin/chromedriver"
            service = ChromeService(executable_path=path)
            driver = webdriver.Chrome(service=service, options=chrome_options)

            try:
                # Clear cookies and cache
                driver.delete_all_cookies()

                # Navigate to the login page
                driver.get(login_url)
                print(f"Navigated to login page: {login_url}")
                if username and password and username_xpath:
                    # Find and fill the username and password fields
                    WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.XPATH, username_xpath)))
                    driver.find_element(By.XPATH, username_xpath).send_keys(username)
                    driver.find_element(By.XPATH, password_xpath).send_keys(password)
                    print("Filled in username and password")

                    # Submit the login form
                    driver.find_element(By.XPATH, login_xpath).click()
                    print("Submitted login form")
                    
                    time.sleep(3)

                    # Check if the page redirects or stays on the same page
                    try:
                        WebDriverWait(driver, 30).until(EC.url_changes(login_url))
                        print("Redirected after login")
                    except TimeoutException:
                        print("Page did not redirect after login")

                if file_download_url:

                    file_download_url = ensure_https(file_download_url)
                    driver.get(file_download_url)
                    print(f"Navigated to download page: {file_download_url}")
                if file_download_url and ('.pdf' in file_download_url or '.csv' in file_download_url or '.xlsx' in file_download_url):
                    try:
                        # Navigate to the file download URL
                        driver.get(file_download_url)
                        print(f"Navigated to download URL: {file_download_url}")

                        # Wait for the download to complete
                        time.sleep(10)  # Adjust this time based on file size and download speed

                        # Verify the downloaded file
                        downloaded_file = wait_for_download_complete(temp_dir)
                        print("Download complete:", downloaded_file)

                        if downloaded_file:
                            domain_name = get_domain_name(login_url)

                            if inventory:
                                directory_path = os.path.join(settings.MEDIA_ROOT, domain_name, 'inventory')
                            else:
                                directory_path = os.path.join(settings.MEDIA_ROOT, domain_name, 'price')

                            if not os.path.exists(directory_path):
                                os.makedirs(directory_path)

                            # Move the file to the specified directory
                            target_path = os.path.join(directory_path, os.path.basename(downloaded_file))
                            print(f"Moving file to: {target_path}")
                            shutil.move(downloaded_file, target_path)
                            relative_path = os.path.relpath(target_path, settings.MEDIA_ROOT)
                            print(f"File saved at: {relative_path}")

                            vendor_log.file_download = True
                            vendor_log.save()

                            vendor_file = VendorSourceFile.objects.create(
                                vendor=vendor_log.vendor
                            )
                            if inventory:
                                vendor_file.inventory_document = relative_path
                                vendor_file.save()
                            else:
                                vendor_file.price_document = relative_path
                                vendor_file.save()

                            ftp_detail = FtpDetail.objects.all().last()
                            print(f"File saved at: {ftp_detail}")
                            if ftp_detail:
                                print(f"ftp_detail: {ftp_detail}")

                                try:
                                    ftp_server = connect_ftp(ftp_detail.host, ftp_detail.username, ftp_detail.password)
                                except Exception as e:
                                    message = "Not able to connect to FTP Server"
                                    print(f"FTP connection error: {message}")

                                    vendor_log.reason = message
                                    vendor_log.save()
                                else:
                                    try:
                                        print(f"Inside FTP server block: {ftp_detail}")
                                        if inventory:
                                            inventory_relative_path = get_relative_path(vendor_file.inventory_document, settings.MEDIA_ROOT)
                                            print(f"Inventory relative path: {inventory_relative_path}")
                                            ftp_upload_file(ftp_server, inventory_relative_path)
                                        else:
                                            price_relative_path = get_relative_path(vendor_file.price_document, settings.MEDIA_ROOT)
                                            print(f"Price relative path: {price_relative_path}")
                                            ftp_upload_file(ftp_server, price_relative_path)
                                        print("File uploaded to FTP server")

                                        vendor_log.file_upload = True
                                        vendor_log.save()
                                    except Exception as e:
                                        vendor_log.reason = str(e)
                                        vendor_log.save()
                                    finally:
                                        disconnect_ftp(ftp_server)
                            else:
                                message = "No FTP Detail Found"
                                vendor_log.reason = message
                                vendor_log.save()
                        else:
                            message = "Invalid Xpaths or download failed"
                            vendor_log.reason = message
                            vendor_log.save()
                            return False
                    finally:
                        driver.quit()
                        return True
                # Find the download link
                if file_download_xpath:
                    download_link = WebDriverWait(driver, 30).until(
                        EC.presence_of_element_located((By.XPATH, file_download_xpath))
                    )
                else:
                    message = "Invalid Xpaths"
                    vendor_log.reason = message
                    vendor_log.save()
                    return False
                download_url = download_link.get_attribute('href')
                print(f"Download URL: {download_url}")

                if download_url:
                    driver.get(download_url)
                    print(f"Navigated to download page: {download_url}")

                # Check if the URL contains .pdf or .csv
                if '.pdf' in download_url or '.csv' in download_url or '.xlsx' in download_url:
                    # Download the file using requests
                    try:
                        response = requests.get(download_url, stream=True)
                        response.raise_for_status()
                        file_extension = '.pdf' if '.pdf' in download_url else '.csv' if '.csv' in download_url else '.xlsx'
                        downloaded_file = os.path.join(temp_dir, f"downloaded_file{file_extension}")
                        with open(downloaded_file, 'wb') as f:
                            for chunk in response.iter_content(chunk_size=8192):
                                f.write(chunk)
                        print(f"Downloaded file saved at: {downloaded_file}")

                        # Process the downloaded file
                        if downloaded_file:
                            domain_name = get_domain_name(login_url)

                            if inventory:
                                directory_path = os.path.join(settings.MEDIA_ROOT, domain_name, 'inventory')
                            else:
                                directory_path = os.path.join(settings.MEDIA_ROOT, domain_name, 'price')

                            if not os.path.exists(directory_path):
                                os.makedirs(directory_path)

                            # Move the file to the specified directory
                            target_path = os.path.join(directory_path, os.path.basename(downloaded_file))
                            print(f"Moving file to: {target_path}")
                            shutil.move(downloaded_file, target_path)
                            relative_path = os.path.relpath(target_path, settings.MEDIA_ROOT)
                            print(f"File saved at: {relative_path}")

                            vendor_log.file_download = True
                            vendor_log.save()

                            vendor_file = VendorSourceFile.objects.create(
                                vendor=vendor_log.vendor
                            )
                            if inventory:
                                vendor_file.inventory_document = relative_path
                                vendor_file.save()
                            else:
                                vendor_file.price_document = relative_path
                                vendor_file.save()

                            ftp_detail = FtpDetail.objects.all().last()
                            print(f"File saved at: {ftp_detail}")
                            if ftp_detail:
                                print(f"ftp_detail: {ftp_detail}")

                                try:
                                    ftp_server = connect_ftp(ftp_detail.host, ftp_detail.username, ftp_detail.password)
                                except Exception as e:
                                    message = "Not able to connect to FTP Server"
                                    print(f"FTP connection error: {message}")

                                    vendor_log.reason = message
                                    vendor_log.save()
                                else:
                                    try:
                                        print(f"Inside FTP server block: {ftp_detail}")
                                        if inventory:
                                            inventory_relative_path = get_relative_path(vendor_file.inventory_document, settings.MEDIA_ROOT)
                                            print(f"Inventory relative path: {inventory_relative_path}")
                                            ftp_upload_file(ftp_server, inventory_relative_path)
                                        else:
                                            price_relative_path = get_relative_path(vendor_file.price_document, settings.MEDIA_ROOT)
                                            print(f"Price relative path: {price_relative_path}")
                                            ftp_upload_file(ftp_server, price_relative_path)
                                        print("File uploaded to FTP server")

                                        vendor_log.file_upload = True
                                        vendor_log.save()
                                    except Exception as e:
                                        vendor_log.reason = str(e)
                                        vendor_log.save()
                                    finally:
                                        disconnect_ftp(ftp_server)
                            else:
                                message = "No FTP Detail Found"
                                vendor_log.reason = message
                                vendor_log.save()
                    except RequestException as e:
                        print(f"Request error: {e}")
                        vendor_log.reason = str(e)
                        vendor_log.save()
                        return False

                else:
                    # Continue with the existing click-based download process
                    download_link.click()
                    print("Clicked download link")

                    # Wait for the download to complete
                    downloaded_file = wait_for_download_complete(temp_dir)
                    print("Download complete:", downloaded_file)

                    if downloaded_file:
                        domain_name = get_domain_name(login_url)

                        if inventory:
                            directory_path = os.path.join(settings.MEDIA_ROOT, domain_name, 'inventory')
                        else:
                            directory_path = os.path.join(settings.MEDIA_ROOT, domain_name, 'price')

                        if not os.path.exists(directory_path):
                            os.makedirs(directory_path)

                        # Move the file to the specified directory
                        target_path = os.path.join(directory_path, os.path.basename(downloaded_file))
                        print(f"Moving file to: {target_path}")
                        shutil.move(downloaded_file, target_path)
                        relative_path = os.path.relpath(target_path, settings.MEDIA_ROOT)
                        print(f"File saved at: {relative_path}")

                        vendor_log.file_download = True
                        vendor_log.save()

                        vendor_file = VendorSourceFile.objects.create(
                            vendor=vendor_log.vendor
                        )
                        if inventory:
                            vendor_file.inventory_document = relative_path
                            vendor_file.save()
                        else:
                            vendor_file.price_document = relative_path
                            vendor_file.save()

                        ftp_detail = FtpDetail.objects.all().last()
                        print(f"File saved at: {ftp_detail}")
                        if ftp_detail:
                            print(f"ftp_detail: {ftp_detail}")

                            try:
                                ftp_server = connect_ftp(ftp_detail.host, ftp_detail.username, ftp_detail.password)
                            except Exception as e:
                                message = "Not able to connect to FTP Server"
                                print(f"FTP connection error: {message}")

                                vendor_log.reason = message
                                vendor_log.save()
                            else:
                                try:
                                    print(f"Inside FTP server block: {ftp_detail}")
                                    if inventory:
                                        inventory_relative_path = get_relative_path(vendor_file.inventory_document, settings.MEDIA_ROOT)
                                        print(f"Inventory relative path: {inventory_relative_path}")
                                        ftp_upload_file(ftp_server, inventory_relative_path)
                                    else:
                                        price_relative_path = get_relative_path(vendor_file.price_document, settings.MEDIA_ROOT)
                                        print(f"Price relative path: {price_relative_path}")
                                        ftp_upload_file(ftp_server, price_relative_path)
                                    print("File uploaded to FTP server")

                                    vendor_log.file_upload = True
                                    vendor_log.save()
                                except Exception as e:
                                    vendor_log.reason = str(e)
                                    vendor_log.save()
                                finally:
                                    disconnect_ftp(ftp_server)
                        else:
                            message = "No FTP Detail Found"
                            vendor_log.reason = message
                            vendor_log.save()
                    else:
                        message = "Invalid Xpaths or download failed"
                        vendor_log.reason = message
                        vendor_log.save()
                        return False


            except Exception as e:
                print(f"An error occurred: {e}")
                message = "Not able to get the Login page"
                vendor_log.reason = message
                vendor_log.save()
                return False

            finally:
                # Close the WebDriver
                driver.quit()
                return True
    except SoftTimeLimitExceeded:
        # Handle the soft time limit exceeded
        print("Task exceeded soft time limit"
              )
        message = "Task exceeded soft download time limit"
        vendor_log.reason = message
        vendor_log.save()
        return True



# def login_and_download_file(login_url, username, password, username_xpath, password_xpath, login_xpath, file_download_xpath, vendor, inventory, file_download_url=""):
#     # Create a temporary directory for downloads
#     try:
#         vendor_source = VendorSource.objects.filter(id=vendor).last()
#         vendor_log = VendorLogs.objects.create(vendor=vendor_source)
#         with tempfile.TemporaryDirectory() as temp_dir:
#             # Configure Chrome options
#             chrome_options = Options()
#             chrome_options.add_argument("--headless")  # Run in headless mode
#             chrome_options.add_argument("--no-sandbox")
#             chrome_options.add_argument("--disable-dev-shm-usage")
#             chrome_options.add_argument("--disable-popup-blocking")  # Disable popup blocking

#             # Set download preferences to use the temporary directory
#             prefs = {
#                 "download.default_directory": temp_dir,
#                 "download.prompt_for_download": False,
#                 "download.directory_upgrade": True,
#                 "safebrowsing.enabled": True
#             }
#             chrome_options.add_experimental_option("prefs", prefs)

#             # Initialize the WebDriver
#             driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)
#             #for Server Use
#             # path = "/usr/bin/chromedriver"
#             # service = ChromeService(executable_path=path)
#             # driver = webdriver.Chrome(service=service, options=chrome_options)

            
#             try:
#                 # Navigate to the login page
#                 driver.get(login_url)
#                 print(f"Navigated to login page: {login_url}")
#                 if username and password and username_xpath:
#                     # Find and fill the username and password fields
#                     driver.find_element(By.XPATH, username_xpath).send_keys(username)
#                     driver.find_element(By.XPATH, password_xpath).send_keys(password)
#                     print("Filled in username and password")

#                     # Submit the login form
#                     driver.find_element(By.XPATH, login_xpath).click()
#                     print("Submitted login form")

#                     # Check if the page redirects or stays on the same page
#                     try:
#                         WebDriverWait(driver, 30).until(EC.url_changes(login_url))
#                         print("Redirected after login")
#                     except TimeoutException:
#                         print("Page did not redirect after login")
#                 if file_download_url:
#                     file_download_url= ensure_https(file_download_url)
#                     driver.get(file_download_url)
#                     print(f"Navigated to download page: {file_download_url}")
                
#                 # Find the download link
#                 try:
#                     download_link = WebDriverWait(driver, 30).until(
#                         EC.presence_of_element_located((By.XPATH, file_download_xpath))
#                     )
#                     download_url = download_link.get_attribute('href')
#                     print(f"Download URL: {download_url}")
#                     # Check if the URL contains .pdf or .csv
#                     if '.pdf' in download_url or '.csv' in download_url or '.xlsx' in download_url:
#                         # Download the file using requests
#                         try:
#                             response = requests.get(download_url, stream=True)
#                             response.raise_for_status()
#                             file_extension = '.pdf' if '.pdf' in download_url else '.csv'
#                             downloaded_file = os.path.join(temp_dir, f"downloaded_file{file_extension}")
#                             with open(downloaded_file, 'wb') as f:
#                                 for chunk in response.iter_content(chunk_size=8192):
#                                     f.write(chunk)
#                             print(f"Downloaded file saved at: {downloaded_file}")

#                             # Process the downloaded file
#                             if downloaded_file:
#                                 domain_name = get_domain_name(login_url)

#                                 if inventory:
#                                     directory_path = os.path.join(settings.MEDIA_ROOT, domain_name, 'inventory')
#                                 else:
#                                     directory_path = os.path.join(settings.MEDIA_ROOT, domain_name, 'price')

#                                 if not os.path.exists(directory_path):
#                                     os.makedirs(directory_path)

#                                 # Move the file to the specified directory
#                                 target_path = os.path.join(directory_path, os.path.basename(downloaded_file))
#                                 print(f"Moving file to: {target_path}")
#                                 shutil.move(downloaded_file, target_path)
#                                 relative_path = os.path.relpath(target_path, settings.MEDIA_ROOT)
#                                 print(f"File saved at: {relative_path}")

#                                 vendor_log.file_download = True
#                                 vendor_log.save()

#                                 vendor_file = VendorSourceFile.objects.create(
#                                     vendor=vendor_log.vendor
#                                 )
#                                 if inventory:
#                                     vendor_file.inventory_document = relative_path
#                                     vendor_file.save()
#                                 else:
#                                     vendor_file.price_document = relative_path
#                                     vendor_file.save()

#                                 ftp_detail = FtpDetail.objects.all().last()
#                                 print(f"File saved at: {ftp_detail}")
#                                 if ftp_detail:
#                                     print(f"ftp_detail: {ftp_detail}")

#                                     try:
#                                         ftp_server = connect_ftp(ftp_detail.host, ftp_detail.username, ftp_detail.password)
#                                     except Exception as e:
#                                         message = "Not able to connect to FTP Server"
#                                         print(f"FTP connection error: {message}")

#                                         vendor_log.reason = message
#                                         vendor_log.save()
#                                     else:
#                                         try:
#                                             print(f"Inside FTP server block: {ftp_detail}")
#                                             if inventory:
#                                                 inventory_relative_path = get_relative_path(vendor_file.inventory_document, settings.MEDIA_ROOT)
#                                                 print(f"Inventory relative path: {inventory_relative_path}")
#                                                 ftp_upload_file(ftp_server, inventory_relative_path)
#                                             else:
#                                                 price_relative_path = get_relative_path(vendor_file.price_document, settings.MEDIA_ROOT)
#                                                 print(f"Price relative path: {price_relative_path}")
#                                                 ftp_upload_file(ftp_server, price_relative_path)
#                                             print("File uploaded to FTP server")

#                                             vendor_log.file_upload = True
#                                             vendor_log.save()
#                                         except Exception as e:
#                                             vendor_log.reason = str(e)
#                                             vendor_log.save()
#                                         finally:
#                                             disconnect_ftp(ftp_server)
#                                 else:
#                                     message = "No FTP Detail Found"
#                                     vendor_log.reason = message
#                                     vendor_log.save()
#                         except RequestException as e:
#                             print(f"Request error: {e}")
#                             vendor_log.reason = str(e)
#                             vendor_log.save()
#                             return False

#                     else:
#                         # Continue with the existing click-based download process
#                         download_link.click()
#                         print("Clicked download link")
                        
#                         # Wait for the download to complete
#                         downloaded_file = wait_for_download_complete(temp_dir)
#                         print("Download complete:", downloaded_file)

#                         if downloaded_file:
#                             domain_name = get_domain_name(login_url)

#                             if inventory:
#                                 directory_path = os.path.join(settings.MEDIA_ROOT, domain_name, 'inventory')
#                             else:
#                                 directory_path = os.path.join(settings.MEDIA_ROOT, domain_name, 'price')

#                             if not os.path.exists(directory_path):
#                                 os.makedirs(directory_path)

#                             # Move the file to the specified directory
#                             target_path = os.path.join(directory_path, os.path.basename(downloaded_file))
#                             print(f"Moving file to: {target_path}")
#                             shutil.move(downloaded_file, target_path)
#                             relative_path = os.path.relpath(target_path, settings.MEDIA_ROOT)
#                             print(f"File saved at: {relative_path}")

#                             vendor_log.file_download = True
#                             vendor_log.save()

#                             vendor_file = VendorSourceFile.objects.create(
#                                 vendor=vendor_log.vendor
#                             )
#                             if inventory:
#                                 vendor_file.inventory_document = relative_path
#                                 vendor_file.save()
#                             else:
#                                 vendor_file.price_document = relative_path
#                                 vendor_file.save()

#                             ftp_detail = FtpDetail.objects.all().last()
#                             print(f"File saved at: {ftp_detail}")
#                             if ftp_detail:
#                                 print(f"ftp_detail: {ftp_detail}")

#                                 try:
#                                     ftp_server = connect_ftp(ftp_detail.host, ftp_detail.username, ftp_detail.password)
#                                 except Exception as e:
#                                     message = "Not able to connect to FTP Server"
#                                     print(f"FTP connection error: {message}")

#                                     vendor_log.reason = message
#                                     vendor_log.save()
#                                 else:
#                                     try:
#                                         print(f"Inside FTP server block: {ftp_detail}")
#                                         if inventory:
#                                             inventory_relative_path = get_relative_path(vendor_file.inventory_document, settings.MEDIA_ROOT)
#                                             print(f"Inventory relative path: {inventory_relative_path}")
#                                             ftp_upload_file(ftp_server, inventory_relative_path)
#                                         else:
#                                             price_relative_path = get_relative_path(vendor_file.price_document, settings.MEDIA_ROOT)
#                                             print(f"Price relative path: {price_relative_path}")
#                                             ftp_upload_file(ftp_server, price_relative_path)
#                                         print("File uploaded to FTP server")

#                                         vendor_log.file_upload = True
#                                         vendor_log.save()
#                                     except Exception as e:
#                                         vendor_log.reason = str(e)
#                                         vendor_log.save()
#                                     finally:
#                                         disconnect_ftp(ftp_server)
#                             else:
#                                 message = "No FTP Detail Found"
#                                 vendor_log.reason = message
#                                 vendor_log.save()
#                         else:
#                             message = "Invalid Xpaths or download failed"
#                             vendor_log.reason = message
#                             vendor_log.save()
#                             return False

#                 except Exception as e:
#                     print(f"An error occurred while finding download link: {e}")
#                     message = "Not able to download File"
#                     vendor_log.reason = message
#                     vendor_log.save()
#                     return False

#             except Exception as e:
#                 print(f"An error occurred: {e}")
#                 message = "Not able to get the Login page"
#                 vendor_log.reason = message
#                 vendor_log.save()
#                 return False

#             finally:
#                 # Close the WebDriver
#                 driver.quit()
#                 return True
#     except SoftTimeLimitExceeded:
#         # Handle the soft time limit exceeded
#         print("Task exceeded soft time limit"
#               )
#         message = "Task exceeded soft download time limit"
#         vendor_log.reason = message
#         vendor_log.save()
#         return True


@shared_task
def ftp_upload_file(ftp_server, file_path):
    # Check if the file exists
    if not os.path.isfile(f"{settings.MEDIA_ROOT}/{file_path}"):
        raise FileNotFoundError(f"The file {file_path} does not exist.")
    
    # Extract the filename from the full file path
    file_name = os.path.basename(file_path)
    # Extract the directory path from the full file path
    directory_path = os.path.dirname(file_path)

    
    # Change to root directory
    ftp_server.cwd('/')
    
    # Split the directory path into components
    directories = directory_path.split(os.path.sep)
    
    # Navigate through directories
    for directory in directories:
        if directory:
            try:
                # Attempt to change into the directory
                ftp_server.cwd(directory)
            except Exception as e:
                if str(e).startswith('550'):
                    # Directory does not exist, so create it
                    ftp_server.mkd(directory)
                    ftp_server.cwd(directory)
                else:
                    # Some other FTP error
                    raise

    # Upload the file
    with open(f"{settings.MEDIA_ROOT}/{file_path}", "rb") as file:
        ftp_server.storbinary(f"STOR {file_name}", file)

    print(f"File {file_path} successfully uploaded to FTP server.")


@shared_task
def scrape_data_to_csv(url, xpath, inventory):
    '''
        Method to download csv file from the given url and xpath
    '''
    try:
        # Make a request to the website
        response = requests.get(url)
        response.raise_for_status()  # Check if the request was successful
        
        # Example: Assuming each element in data is a row of values
        # Adjust this part based on the actual structure of your data
        tree = html.fromstring(response.content)
        domain_name = get_domain_name(url)
        if inventory:
            scrape_inventory(tree, domain_name, url, xpath)
        else:
            scrape_price(tree, domain_name, url, xpath)
        
    except requests.exceptions.RequestException as e:
        print(f"HTTP request failed: {e}")
        return False, None, str(e)




@shared_task
def process_due_vendors():
    """
    Task to check all VendorSource records and run `login_and_download_file` if due.
    """
    import json
    today = datetime.now().date()  # Get current date
    from core_app.models import VendorSource
    vendors = VendorSource.objects.all()
    print(today)
    for vendor in vendors:
        if vendor.updated_at and vendor.interval is not None and vendor.unit:
            # Calculate the target date based on the unit
            if vendor.unit == 'days':
                delta = timedelta(days=vendor.interval)
            elif vendor.unit == 'weeks':
                delta = timedelta(weeks=vendor.interval)
            elif vendor.unit == 'hours':
                delta = timedelta(hours=vendor.interval)
            else:
                print(f"Unsupported unit '{vendor.unit}' for vendor {vendor.website}.")
                continue

            target_date = vendor.updated_at.date() + delta
            # Check if today's date matches the target date
            if today == target_date:
                # Check if username and password are present
                if vendor.username and vendor.password:
                    xpath_data = json.loads(vendor.xpath)
                    # Run the login_and_download_file function
                    login_and_download_file.delay(
                        login_url=vendor.website,
                        username=vendor.username,
                        password=vendor.password,
                        username_xpath=xpath_data.get('username_xpath', ''),
                        password_xpath=xpath_data.get('password_xpath', ''),
                        login_xpath=xpath_data.get('login_button_xpath', ''),
                        file_download_xpath=xpath_data.get('inventory', ''),
                        vendor=vendor.id,
                        inventory=True, # or False based on your needs
                        file_download_url=vendor.file_url
                    )
                    login_and_download_file.delay(
                        login_url=vendor.website,
                        username=vendor.username,
                        password=vendor.password,
                        username_xpath=xpath_data.get('username_xpath', ''),
                        password_xpath=xpath_data.get('password_xpath', ''),
                        login_xpath=xpath_data.get('login_button_xpath', ''),
                        file_download_xpath=xpath_data.get('price', ''),
                        vendor=vendor.id,
                        inventory=False,  # or False based on your needs
                        file_download_url=vendor.file_url
                    )
                else:
                    print(f"Vendor {vendor.website} does not have username or password.")
            else:
                print(f"Vendor {vendor.website} is not due today. Target date: {target_date}.")
