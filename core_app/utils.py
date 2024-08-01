import requests
from urllib.parse import urlparse
from django.conf import settings
import os 
import re

from selenium.webdriver.support.ui import WebDriverWait
import time
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import shutil
import tempfile
import logging
from datetime import datetime, timedelta
from lxml import html


logger = logging.getLogger(__name__)

def get_domain_name(url):
    '''
        Method to get domain name from url
    '''
    try:
        # Parse the URL
        parsed_url = urlparse(url)
        
        # Extract the domain name (netloc)
        domain_name = parsed_url.netloc
        
        # Handle cases where the URL might have www or other subdomains
        if domain_name.startswith('www.'):
            domain_name = domain_name[4:]
            domain  = domain_name
            domain_name = domain.split('.')
            return domain_name[0]
    except Exception as e:
        print(f"Error parsing URL: {e}")
        return None


def is_valid_url(url):
    """
    Validate if the entered string is a valid website URL format.

    Args:
        url (str): The URL string to validate.

    Returns:
        bool: True if valid, False otherwise.
    """
    # Regular expression to match a valid URL
    regex = re.compile(
        r'^(?:http|ftp)s?://' # http:// or https:// or ftp:// or ftps://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' # domain...
        r'localhost|' # localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}|' # ...or ipv4
        r'\[?[A-F0-9]*:[A-F0-9:]+\]?)' # ...or ipv6
        r'(?::\d+)?' # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)

    return re.match(regex, url) is not None

def get_most_recent_file(directory, extension='.csv'):
    """Get the most recently modified file in the directory with the specified extension."""
    files = [os.path.join(directory, f) for f in os.listdir(directory) if f.endswith(extension)]
    if not files:
        return None
    return max(files, key=os.path.getmtime)


def wait_for_download_complete(download_dir, timeout=120):
    """Wait for the file download to complete."""
    start_time = time.time()
    while True:
        # Get list of files in download directory
        files = [os.path.join(download_dir, f) for f in os.listdir(download_dir)]
        if files:
            # Get the most recently modified file
            latest_file = max(files, key=os.path.getmtime)
            # Check if the file size remains constant for a period of time
            try:
                initial_size = os.path.getsize(latest_file)
                time.sleep(5)  # Wait for a while
                final_size = os.path.getsize(latest_file)
                if initial_size == final_size:
                    return latest_file
            except FileNotFoundError:
                # File might be deleted if the download failed
                continue
        # Check if we have exceeded the timeout
        if time.time() - start_time > timeout:
            print("Download did not complete in time.")
            return None
        time.sleep(1)  # Wait before checking again

def login_and_download_file(login_url, username, password, username_xpath, password_xpath, login_xpath, file_download_xpath, inventory):
    # Create a temporary directory for downloads
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
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

        try:
            # Navigate to the login page
            driver.get(login_url)
            print(f"Navigated to login page: {login_url}")

            # Find and fill the username and password fields
            driver.find_element(By.XPATH, username_xpath).send_keys(username)
            driver.find_element(By.XPATH, password_xpath).send_keys(password)
            print("Filled in username and password")

            # Submit the login form
            driver.find_element(By.XPATH, login_xpath).click()
            print("Submitted login form")

            # Wait for redirection or page load
            WebDriverWait(driver, 10).until(EC.url_changes(login_url))
            print("Redirected after login")

            # Find and click the download link
            download_link = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, file_download_xpath))
            )
            download_url = download_link.get_attribute('href')
            print(f"Download URL: {download_url}")

            # Initiate the download
            download_link.click()
            print("Clicked download link")

            # Wait for the download to complete
            downloaded_file = wait_for_download_complete(temp_dir)
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
                
                return relative_path, domain_name, None

            else:
                print("No downloaded file found.")
                return None, domain_name, None

        except Exception as e:
            print(f"An error occurred: {e}")
            
            return None, None, str(e)

        finally:
            # Close the WebDriver
            driver.quit()
            return relative_path, domain_name

   
def scrape_data_to_csv(url, username=None, password=None):
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
        return tree, domain_name, None
    except requests.exceptions.RequestException as e:
        print(f"HTTP request failed: {e}")
        return False, None, str(e)



def scrape_inventory(tree_obj, domain_name, url, inventory_xpath):
        
    # Extract the link to the CSV file using XPath
    inventory_csv_links = tree_obj.xpath(inventory_xpath)
    if inventory_csv_links:
        csv_link_element = inventory_csv_links[0]
        
        csv_url = csv_link_element.get('href')
        
        if not csv_url:
            raise ValueError("No CSV link found for the given XPath")
        
        link_text = csv_link_element.text_content().strip()
        extension = link_text.split('.')
        directory_path = os.path.join(settings.MEDIA_ROOT, domain_name, 'inventory')
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)
        csv_filename =  os.path.join(directory_path, link_text)
        inventory_relative_path = os.path.relpath(csv_filename, settings.MEDIA_ROOT)
        if extension[1] in ['csv', 'xlsx']:
            # Handle relative URLs
            if not csv_url.startswith('http'):
                from urllib.parse import urljoin
                csv_url = urljoin(url, csv_url)

            # Download the CSV file
            csv_response = requests.get(csv_url)
            csv_response.raise_for_status()  # Check if the request was successful
            # Save the CSV file to the specified download path
            with open(csv_filename, 'wb') as f:
                f.write(csv_response.content)
        
            print(f"Data successfully saved to {csv_filename}")
            return inventory_relative_path, True, None

    return False, None, 'Download Link Not Found'

def scrape_price(tree_obj, domain_name, url, price_xpath):
    price_csv_links = tree_obj.xpath(price_xpath)
    if price_csv_links:
        csv_link_element = price_csv_links[0]
        
        csv_url = csv_link_element.get('href')
        
        if not csv_url:
            raise ValueError("No CSV link found for the given XPath")
        
        link_text = csv_link_element.text_content().strip()
        extension = link_text.split('.')
        directory_path = os.path.join(settings.MEDIA_ROOT, domain_name, 'price')
        if not os.path.exists(directory_path):
            os.makedirs(directory_path)
        csv_filename =  os.path.join(directory_path, link_text)
        relative_path = os.path.relpath(csv_filename, settings.MEDIA_ROOT)
        if extension[1] in ['csv', 'xlsx']:
            # Handle relative URLs
            if not csv_url.startswith('http'):
                from urllib.parse import urljoin
                csv_url = urljoin(url, csv_url)

            # Download the CSV file
            csv_response = requests.get(csv_url)
            csv_response.raise_for_status()  # Check if the request was successful
            # Save the CSV file to the specified download path
            with open(csv_filename, 'wb') as f:
                f.write(csv_response.content)
        
            print(f"Data successfully saved to {csv_filename}")
            return relative_path, True, None
    return False, None,  'Download Link Not Found'

def get_relative_path(file_field, media_root):
    # Get the absolute path of the file
    absolute_path = str(file_field.path)
    media_root = str(media_root)
    
    # Compute the relative path by removing MEDIA_ROOT from the absolute path
    if absolute_path.startswith(media_root):
        relative_path = os.path.relpath(absolute_path, media_root)
    else:
        raise ValueError(f"The file path {absolute_path} does not start with MEDIA_ROOT {media_root}.")
    
    return relative_path


def connect_ftp(HOSTNAME, USERNAME, PASSWORD):
    
    # Import Module
    import ftplib
    
    # Connect FTP Server
    ftp_server = ftplib.FTP(HOSTNAME, USERNAME, PASSWORD)
     
    # force UTF-8 encoding
    ftp_server.encoding = "utf-8"
     
    return ftp_server

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


def disconnect_ftp(ftp_server):
      
    # Close the Connection
    ftp_server.quit()


def check_and_run_task(created_at, interval_days):
    """
    Checks if the current date matches the created_at date plus the interval.
    If it matches, run the Celery task.

    :param created_at: The date the record was created
    :param interval_days: The interval in days after which the task should be run
    """
    from .models import VendorSource
    vendors = VendorSource.objects.all()
    # Calculate the target date
    run_task_vendors = []
    for vendor in vendors:
        target_date = vendor.created_at + timedelta(days=vendor.interval_days)
        
        # Get the current date
        current_date = datetime.now().date()
        
        # Check if today matches the target date
        if current_date == target_date:
            run_task_vendors.append(vendor.id)
            
