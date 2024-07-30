import requests
from lxml import html
import pandas as pd
from urllib.parse import urlparse
from django.conf import settings
import os 
import re


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
        return tree, domain_name
    except requests.exceptions.RequestException as e:
        print(f"HTTP request failed: {e}")
        return False, None



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
                return True, inventory_relative_path

    return False, None
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
            return True, relative_path
    return False, None

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