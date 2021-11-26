import gspread
from oauth2client.service_account import ServiceAccountCredentials
from re import search, findall
from time import sleep
from bs4 import BeautifulSoup
import requests
from tqdm import tqdm
import json


LINK = 4
PID = 5
BULK_QUANTITY = 7
BULK_PRICE = 8
SINGLE_PRICE = 10
STOCK = 12

START = 4
END = 74

SHEET_NAME = "Copy of USA Kits Prices"


class Mouser():
    def __init__(self):
        with open("creds.json") as f:
            key = json.load(f)["apiKey"]
        self.url = f"https://api.mouser.com/api/v1/search/partnumber?apiKey={key}"
        self.json_data = {"SearchByPartRequest": {
            "mouserPartNumber": "",
            "partSearchOptions": ""
        }}

    def set_number(self, num):
        self.json_data["SearchByPartRequest"]["mouserPartNumber"] = num

    def get_stock(self):
        info = self.response["SearchResults"]["Parts"][0]["Availability"]
        if search("In Stock", info):
            return search(r"[0-9]*", info).group()
        else:
            return "0"

    def get_single(self):
        return search(r"[0-9]+\.?([0-9]+)?", self.response["SearchResults"]["Parts"][0]["PriceBreaks"][0]["Price"]).group()

    def get_bulk(self, quantity):
        # set variables
        quantity = int(quantity)
        q_list = []

        # get quantities
        for i in self.response["SearchResults"]["Parts"][0]["PriceBreaks"]:
            q_list.append(i["Quantity"])
        
        # find closest quantity to requested
        index = 0
        diff = 100000
        found_q = 0
        for i, q in enumerate(q_list):
            if abs(quantity-q) < diff:
                index = i
                diff = abs(quantity-q)
                found_q = q

        # if found quantity smaller than requested, take one higher
        if found_q<quantity:
            if index+1 < len(q_list):
                index+=1

        return search(r"[0-9]+\.?([0-9]+)?", self.response["SearchResults"]["Parts"][0]["PriceBreaks"][index]["Price"]).group()

    def run(self, pid, bulk_quantity, skip_bulk):
        self.set_number(pid)
        self.response = requests.post(self.url, json=self.json_data).json()

        stock = self.get_stock()
        single = self.get_single()
        if skip_bulk:
            bulk = "???"
        else:
            bulk = self.get_bulk(bulk_quantity)

        return stock, single, bulk



class Lcsc():
    def get_stock(self):
        info = str(self.content.find('div', class_="head"))
        if search("In Stock", info):
            return search(r"In Stock: [0-9]*", info).group().split(" ")[-1]
        elif search("General", info):
            return "N/A"
        else:
            return "0"
        

    def get_single(self):
        info = self.content.find('div', class_="box ladder-price")
        info = str(info.find_all('tr'))
        return search(r"US\$[0-9]*\.[0-9]*", info).group().split('$')[1]

    def get_bulk(self, quantity):
        quantity = int(quantity)
        info = self.content.find('div', class_="box ladder-price")
        info = str(info.find_all('tr'))

        # find closest quantity to requested
        index = 0
        diff = 100000
        found_q = 0
        q_list = [i[:-1] for i in findall(r"[0-9]*\+", info)]
        for i, q in enumerate(q_list):
            q = int(q)
            if abs(quantity-q) < diff:
                index = i
                diff = abs(quantity-q)
                found_q = q

        # if found quantity smaller than requested, take one higher
        if found_q<quantity:
            if index+1 < len(q_list):
                index+=1

        return [i.split("$")[1] for i in findall(r"US\$[0-9]*\.[0-9]*", info)][index]

    def run(self, url, bulk_quantity, skip_bulk):
        page = requests.get(url)
        self.content = BeautifulSoup(page.content, 'html.parser')

        stock = self.get_stock()
        if stock != "N/A":
            single = self.get_single()
            if skip_bulk:
                bulk = "???"
            else:
                bulk = self.get_bulk(bulk_quantity)
        else:
            single = '0'
            bulk = '0'

        return stock, single, bulk


# get sheet
scope = ["https://spreadsheets.google.com/feeds",'https://www.googleapis.com/auth/spreadsheets',"https://www.googleapis.com/auth/drive.file","https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name("creds.json", scope)
client = gspread.authorize(creds)
sheet = client.open(SHEET_NAME).sheet1

# initialize classes
mouser = Mouser()
lcsc = Lcsc()

#for each product:

for i in tqdm(range(START, END+1)):
    # fetch link if available, check if bulk quantity is available
    link = sheet.cell(i, LINK).value
    if link == None or link == "???":
        sheet.update_cell(i, LINK, "???")
        continue
    sleep(1)

    skip_bulk = False
    if sheet.cell(i, BULK_QUANTITY).value == None or sheet.cell(i, BULK_QUANTITY).value == "???":
        skip_bulk = True

    update = False

    # get product info
    if search("mouser.com", link):
        update = True
        if sheet.cell(i, PID).value == None or sheet.cell(i, PID).value == "???":
            sheet.update_cell(i, PID, "???")
            continue
        stock, single, bulk = mouser.run(sheet.cell(i, PID).value, sheet.cell(i, BULK_QUANTITY).value, skip_bulk)
    elif search("lcsc.com", link):
        update = True
        stock, single, bulk = lcsc.run(sheet.cell(i, LINK).value, sheet.cell(i, BULK_QUANTITY).value, skip_bulk)

    # set product info
    if update:
        sheet.update_cell(i, SINGLE_PRICE, single)
        sleep(1)
        if bulk == "???":
            sheet.update_cell(i, BULK_QUANTITY, bulk)
        else:
            sheet.update_cell(i, BULK_PRICE, bulk)
        sleep(1)
        sheet.update_cell(i, STOCK, stock)
        sleep(1)