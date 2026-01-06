import calendar
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import urllib3
from os import listdir, makedirs
from os.path import isfile, join
import argparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import sys
from dateutil.relativedelta import relativedelta


urllib3.disable_warnings()

A3_UNITS_LIST = []
LAST_CY_ORCL_DIVIDENDS_LIST = []
LAST_CY_FIDELITY_INTEREST = 0
ORCL_PEAK_PRICE_MAP = {}
ORCL_CY_CLOSING_PRICE = None
ACCOUNT_PEAK_BALANCE_INR = 0
ACCOUNT_CLOSING_BALANCE_INR = 0
TOTAL_CY_CAPITAL_GAINS = 0
LAST_CY_TXN_LIST = []
CURRENT_CY_TXN_LIST = []
OPEN_LOTS_FILE = None
CLOSED_LOTS_FILE = None

CURRENT_TAX_YEAR = None
ACCOUNT_STARTING_CASH_RESERVE_BALANCE_USD = 0
PARTICIPANT_NUMBER = None
ACCOUNT_OPENING_DATE = None
TT_BUY_RATE_CSV_URI = "https://raw.githubusercontent.com/sahilgupta/sbi-fx-ratekeeper/refs/heads/main/csv_files/SBI_REFERENCE_RATES_USD.csv"

TT_BUY_MAP = dict()

def init(args):
    csv_files = [join(args.files_dir, f) for f in listdir(args.files_dir) if isfile(join(args.files_dir, f)) and f[-4:] == ".csv"]
    global ACCOUNT_STARTING_CASH_RESERVE_BALANCE_USD, PARTICIPANT_NUMBER, ACCOUNT_OPENING_DATE, OPEN_LOTS_FILE, CLOSED_LOTS_FILE, LAST_CY_TXN_LIST, CURRENT_CY_TXN_LIST
    ACCOUNT_STARTING_CASH_RESERVE_BALANCE_USD = args.opening_cash_balance
    PARTICIPANT_NUMBER = args.participant_account_number
    ACCOUNT_OPENING_DATE = args.account_open_date
    OPEN_LOTS_FILE = [f for f in csv_files if "open lots" in f][0]
    CLOSED_LOTS_FILE = [f for f in csv_files if "closed lots" in f][0]
    file = open(CLOSED_LOTS_FILE, "r")
    lines = file.read().splitlines()
    file.close()
    for line in lines:
        fields = line.split(",")
        try:
            datetime.strptime(fields[0], "%b/%d/%Y")
            if len(fields) < 8 or fields[7] not in ["SP", "RS"]:
                print("RS/SP not specified as last column in closed lots CSV. Exiting.")
                sys.exit(-1)
        except ValueError:
            continue
    for f in csv_files:
        if f not in [OPEN_LOTS_FILE, CLOSED_LOTS_FILE]:
            file = open(f, "r")
            lines = file.read().splitlines()
            file.close()
            for line in lines:
                fields = line.split(',')
                try:
                    date = datetime.strptime(fields[0], "%b-%d-%Y")
                    if date.year == CURRENT_TAX_YEAR:
                        CURRENT_CY_TXN_LIST.append(fields)
                    elif date.year == CURRENT_TAX_YEAR-1:
                        LAST_CY_TXN_LIST.append(fields)
                except ValueError:
                    continue
    prompt = []
    if not CURRENT_CY_TXN_LIST:
        prompt.append(str(CURRENT_TAX_YEAR))
    if not LAST_CY_TXN_LIST:
        prompt.append(str(CURRENT_TAX_YEAR-1))
    if prompt:
        while True:
            print(f"No transactions found for {" and ".join(prompt)}. This is unlikely and you might want to check the transaction files you've passed. Confirm if you want to proceed anyway (Y/N): ", end="")
            conf = str(input()).lower()
            if conf in ["y", "n"]:
                break
            else: print("Invalid input passed.")
        if conf == "n":
            sys.exit(-1)
    makedirs(args.output_dir, exist_ok=True)
    fetch_orcl_prices()

def init_tt_buy():
    content = requests.get(TT_BUY_RATE_CSV_URI, verify=False)
    content = content.text.splitlines()

    for line in content[1:]:
        temp = line.split(",")
        TT_BUY_MAP[datetime.strptime(temp[0].split(" ")[0], "%Y-%m-%d")] = float(temp[2])

def get_last_month_and_year(date):
    if date.month == 1:
        return 12, date.year-1
    else: return date.month-1, date.year

def fetch_last_month_tt_buy(date):
    last_month, year = get_last_month_and_year(date)
    _, max_days = calendar.monthrange(year, last_month)
    return fetch_last_available_tt_buy(datetime(year, last_month, max_days))

def fetch_last_available_tt_buy(date):
    while True:
        if date in TT_BUY_MAP:
            return TT_BUY_MAP[date]
        date = date - timedelta(days=1)

def parse_transaction_summary_dividends(summary_list1, summary_list2, output_dir):
    lines = summary_list1 + summary_list2
    # split: 01/04-15/06, 16/06-15/09, 16/09-15/12, 16/12-15/03, 16/03-31/03
    dividend_split = [0, 0, 0, 0, 0]
    dividends_with_tax = 0

    for fields in lines:
        try:
            date = datetime.strptime(fields[0], "%b-%d-%Y")
            if "DIVIDEND RECEIVED" in fields[1] and "TAX" not in fields[1]:
                dividend_amount_in_inr = float(fields[4].replace("$", ""))*fetch_last_month_tt_buy(date)
                if date >= datetime(CURRENT_TAX_YEAR-1, 1, 1) and date < datetime(CURRENT_TAX_YEAR, 1, 1):
                    if fields[2] == "ORACLE CORP":
                        LAST_CY_ORCL_DIVIDENDS_LIST.append({
                            "amount_inr": dividend_amount_in_inr,
                            "date_received": date,
                        })
                    else:
                        global LAST_CY_FIDELITY_INTEREST
                        LAST_CY_FIDELITY_INTEREST += dividend_amount_in_inr
                # print("Dividend found: " + fields[4].replace("$", "") + " from " + fields[2])
                if date >= datetime(CURRENT_TAX_YEAR-1, 4, 1) and date <= datetime(CURRENT_TAX_YEAR-1, 6, 15):
                    if fields[2] == "ORACLE CORP":
                        dividends_with_tax += dividend_amount_in_inr
                    dividend_split[0] += dividend_amount_in_inr
                elif date >= datetime(CURRENT_TAX_YEAR-1, 6, 16) and date <= datetime(CURRENT_TAX_YEAR-1, 9, 15):
                    if fields[2] == "ORACLE CORP":
                        dividends_with_tax += dividend_amount_in_inr
                    dividend_split[1] += dividend_amount_in_inr
                elif date >= datetime(CURRENT_TAX_YEAR-1, 9, 16) and date <= datetime(CURRENT_TAX_YEAR-1, 12, 15):
                    if fields[2] == "ORACLE CORP":
                        dividends_with_tax += dividend_amount_in_inr
                    dividend_split[2] += dividend_amount_in_inr
                elif date >= datetime(CURRENT_TAX_YEAR-1, 12, 16) and date <= datetime(CURRENT_TAX_YEAR, 3, 15):
                    if fields[2] == "ORACLE CORP":
                        dividends_with_tax += dividend_amount_in_inr
                    print(fields[4])
                    dividend_split[3] += dividend_amount_in_inr
                elif date >= datetime(CURRENT_TAX_YEAR, 3, 16) and date <= datetime(CURRENT_TAX_YEAR, 3, 31):
                    if fields[2] == "ORACLE CORP":
                        dividends_with_tax += dividend_amount_in_inr
                    dividend_split[4] += dividend_amount_in_inr
                else:
                    continue
        except ValueError:
            continue
    
    outfile = open(output_dir + f"/FY_{CURRENT_TAX_YEAR-1}-{CURRENT_TAX_YEAR}_dividend_info.txt", "w")
    outfile.write(f"Dividend split for FY:\n01 Apr - 15 Jun: {round(dividend_split[0])}\n16 Jun - 15 Sep: {round(dividend_split[1])}\n16 Sep - 15 Dec: {round(dividend_split[2])}\n16 Dec - 15 Mar: {round(dividend_split[3])}\n16 Mar - 31 Mar: {round(dividend_split[4])}\n")
    outfile.write("\nTotal dividend: " + str(round(sum(dividend_split))))
    outfile.write("\nDividends with tax paid in the US: " + str(round(dividends_with_tax)))
    outfile.write("\nTax paid in US in INR: " + str(round(dividends_with_tax*0.25)))
    outfile.close()

def parse_shares(open_lots_filename, closed_lots_filename, output_dir):
    file = open(open_lots_filename, "r")
    open_lines = file.read().splitlines()
    file.close()
    file = open(closed_lots_filename, "r")
    closed_lines = file.read().splitlines()
    file.close()

    # TODO: Determine long term or short term
    capital_gains_or_loss_split = [[0,0], [0,0], [0,0], [0,0], [0,0]]
    long_term_assets_acquire_value = 0
    long_term_assets_proceeds = 0
    short_term_assets_acquire_value = 0
    short_term_assets_proceeds = 0

    for line in closed_lines:
        fields = line.split(",")
        try:
            date_acquired = datetime.strptime(fields[0], "%b/%d/%Y")
            date_sold = datetime.strptime(fields[2], "%b/%d/%Y")
            peak_start_date = date_acquired
            peak_end_date = date_sold
            if date_acquired < datetime(CURRENT_TAX_YEAR-1, 1, 1):
                peak_start_date = datetime(CURRENT_TAX_YEAR-1, 1, 1)
            if date_sold > datetime(CURRENT_TAX_YEAR-1, 12, 31):
                peak_end_date = datetime(CURRENT_TAX_YEAR, 12, 31)
            if len(fields) < 8 or fields[7] not in ["SP", "RS"]:
                print("RS/SP not specified as last column in closed lots CSV. Exiting.")
                sys.exit(-1)
            if date_sold >= datetime(CURRENT_TAX_YEAR-1, 1, 1) and date_acquired < datetime(CURRENT_TAX_YEAR, 1, 1):
                # Held during CURRENT_YEAR-1 -> Schedule FA
                initial_price = float(fields[4])*(100/95 if fields[7] == "SP" else 1)*fetch_last_month_tt_buy(date_acquired)
                gains = (float(fields[3])*fetch_last_month_tt_buy(date_sold) - initial_price) if date_sold < datetime(CURRENT_TAX_YEAR, 1, 1) else 0
                A3_UNITS_LIST.append({
                    "initial_price": initial_price,
                    "closing_price": get_orcl_closing_price()*fetch_last_available_tt_buy(datetime(CURRENT_TAX_YEAR-1, 12, 31))*float(fields[1]) if date_sold < datetime(CURRENT_TAX_YEAR, 1, 1) else 0,
                    "peak_price": get_orcl_peak_price_inr(peak_start_date, peak_end_date)*float(fields[1]),
                    "proceeds": 0 if date_sold >= datetime(CURRENT_TAX_YEAR, 1, 1) else initial_price + gains,
                    "dividends": 0,
                    "date_sold": date_sold,
                    "qty": float(fields[1]),
                    "date_acquired": date_acquired,
                })
                global TOTAL_CY_CAPITAL_GAINS
                TOTAL_CY_CAPITAL_GAINS += gains
            if date_sold < datetime(CURRENT_TAX_YEAR, 4, 1) and date_sold >= datetime(CURRENT_TAX_YEAR-1, 4, 1):
                initial_price = float(fields[4])*(100/95 if fields[7] == "SP" else 1)*fetch_last_month_tt_buy(date_acquired)
                capital_gains_or_loss_inr = (float(fields[3])*fetch_last_month_tt_buy(date_sold) - initial_price)
                if date_sold >= date_acquired + relativedelta(months=24):
                    idx = 1
                    long_term_assets_acquire_value += initial_price
                    long_term_assets_proceeds += initial_price + capital_gains_or_loss_inr
                else:
                    idx = 0
                    short_term_assets_acquire_value += initial_price
                    short_term_assets_proceeds += initial_price + capital_gains_or_loss_inr
                if date_sold >= datetime(CURRENT_TAX_YEAR-1, 4, 1) and date_sold <= datetime(CURRENT_TAX_YEAR-1, 6, 15):
                    capital_gains_or_loss_split[0][idx] += capital_gains_or_loss_inr
                elif date_sold >= datetime(CURRENT_TAX_YEAR-1, 6, 16) and date_sold <= datetime(CURRENT_TAX_YEAR-1, 9, 15):
                    capital_gains_or_loss_split[1][idx] += capital_gains_or_loss_inr
                elif date_sold >= datetime(CURRENT_TAX_YEAR-1, 9, 16) and date_sold <= datetime(CURRENT_TAX_YEAR-1, 12, 15):
                    capital_gains_or_loss_split[2][idx] += capital_gains_or_loss_inr
                elif date_sold >= datetime(CURRENT_TAX_YEAR-1, 12, 16) and date_sold <= datetime(CURRENT_TAX_YEAR, 3, 15):
                    capital_gains_or_loss_split[3][idx] += capital_gains_or_loss_inr
                elif date_sold >= datetime(CURRENT_TAX_YEAR, 3, 16) and date_sold <= datetime(CURRENT_TAX_YEAR, 3, 31):
                    capital_gains_or_loss_split[4][idx] += capital_gains_or_loss_inr
        except ValueError:
            continue
    outfile = open(output_dir + f"/FY_{CURRENT_TAX_YEAR-1}-{CURRENT_TAX_YEAR}_cg_info.txt", "w")
    outfile.write("Total capital gains in INR: " + str(round(sum([sum(x) for x in capital_gains_or_loss_split]))))
    outfile.write("\n\nTotal short term capital gains: " + str(round(sum([x[0] for x in capital_gains_or_loss_split]))))
    outfile.write(f"\nShort term cost of acquisition: {round(short_term_assets_acquire_value)} Proceeds: {round(short_term_assets_proceeds)}")
    outfile.write(f"\nShort term capital gains split for FY:\n01 Apr - 15 Jun: {round(capital_gains_or_loss_split[0][0])}\n16 Jun - 15 Sep: {round(capital_gains_or_loss_split[1][0])}\n16 Sep - 15 Dec: {round(capital_gains_or_loss_split[2][0])}\n16 Dec - 15 Mar: {round(capital_gains_or_loss_split[3][0])}\n16 Mar - 31 Mar: {round(capital_gains_or_loss_split[4][0])}")
    outfile.write("\n\nTotal long term capital gains: " + str(round(sum([x[1] for x in capital_gains_or_loss_split]))))
    outfile.write(f"\nLong term cost of acquisition: {round(long_term_assets_acquire_value)} Proceeds: {round(long_term_assets_proceeds)}")
    outfile.write(f"\nLong term capital gains split for FY:\n01 Apr - 15 Jun: {round(capital_gains_or_loss_split[0][1])}\n16 Jun - 15 Sep: {round(capital_gains_or_loss_split[1][1])}\n16 Sep - 15 Dec: {round(capital_gains_or_loss_split[2][1])}\n16 Dec - 15 Mar: {round(capital_gains_or_loss_split[3][1])}\n16 Mar - 31 Mar: {round(capital_gains_or_loss_split[4][1])}")
    outfile.close()

    for line in open_lines:
        fields = line.split(",")
        try:
            date_acquired = datetime.strptime(fields[0], "%b-%d-%Y")
            peak_start_date = date_acquired
            if date_acquired < datetime(CURRENT_TAX_YEAR-1, 1, 1):
                peak_start_date = datetime(CURRENT_TAX_YEAR-1, 1, 1)
            if date_acquired < datetime(CURRENT_TAX_YEAR, 1, 1):
                # Held during CURRENT_YEAR-1 -> Schedule FA
                A3_UNITS_LIST.append({
                    "initial_price": float(fields[2])*(100/95 if fields[9] == "SP" else 1)*fetch_last_month_tt_buy(date_acquired),
                    "closing_price": get_orcl_closing_price()*float(fields[1])*fetch_last_available_tt_buy(datetime(CURRENT_TAX_YEAR-1, 12, 31)),
                    "peak_price": get_orcl_peak_price_inr(peak_start_date, datetime(CURRENT_TAX_YEAR-1, 12, 31))*float(fields[1]),
                    "proceeds": 0,
                    "dividends": 0,
                    "qty": float(fields[1]),
                    "date_sold": None,
                    "date_acquired": date_acquired,
                })
        except ValueError:
            continue

def populate_dividends_for_a3():
    for dividend in LAST_CY_ORCL_DIVIDENDS_LIST:
        # Edge case: What happens when sold or received on same day as dividend received?
        number_of_shares_of_dividend = sum([unit["qty"] for unit in A3_UNITS_LIST if (unit["date_sold"] is None or unit["date_sold"] > dividend["date_received"]) and unit["date_acquired"] < dividend["date_received"]])
        for unit in A3_UNITS_LIST:
            if (unit["date_sold"] is None or unit["date_sold"] > dividend["date_received"]) and unit["date_acquired"] < dividend["date_received"]:
                unit["dividends"] += float(float(unit["qty"]/number_of_shares_of_dividend)*dividend["amount_inr"])

def generate_a3_csv(output_dir):
    a3_file = open(output_dir + "/A3_details_orcl_" + str(CURRENT_TAX_YEAR-1) + ".csv", "w")
    a3_file.write("\"Country/Region name\",\"Country Name and Code\",\"Name of entity\",\"Address of entity\",\"ZIP Code\",\"Nature of entity\",\"Date of acquiring the interest\",\"Initial value of the investment\",\"Peak value of investment during the Period\",\"Closing balance\",\"Total gross amount paid/credited with respect to the holding during the period\",\"Total gross proceeds from sale or redemption of investment during the period\",\n")
    for unit in A3_UNITS_LIST:
        a3_file.write("UNITED STATES OF AMERICA,2,ORACLE (ORCL),Oracle Corporation 2300 Oracle Way Austin TX,78741,Company Listed on Stock Exchange,")
        a3_file.write(f"{unit["date_acquired"].strftime("%Y-%m-%d")},{round(unit["initial_price"])},{round(unit["peak_price"])},{round(unit["closing_price"])},{round(unit["dividends"])},{round(unit["proceeds"])},\n")
    a3_file.close()
    print("A3 CSV file generated")

def get_orcl_closing_price():
    return ORCL_CY_CLOSING_PRICE

def get_orcl_peak_date_and_price(start_date, end_date):
    temp_date = start_date
    max_price_so_far = fetch_last_available_orcl_price(start_date)
    max_date = start_date
    while temp_date <= end_date:
        if temp_date in ORCL_PEAK_PRICE_MAP and ORCL_PEAK_PRICE_MAP[temp_date] > max_price_so_far:
            max_price_so_far = ORCL_PEAK_PRICE_MAP[temp_date]
            max_date = temp_date
        temp_date = temp_date + timedelta(days=1)
    return max_date, max_price_so_far

def fetch_last_available_orcl_price(date):
    while True:
        if date < datetime(CURRENT_TAX_YEAR-2, 12, 25):
            return None
        if date in ORCL_PEAK_PRICE_MAP:
            return ORCL_PEAK_PRICE_MAP[date]
        date = date - timedelta(days=1)

def get_orcl_peak_price_inr(start_date, end_date):
    date, price = get_orcl_peak_date_and_price(start_date, end_date)
    if date is None:
        return 0
    return price*fetch_last_available_tt_buy(date)

# TODO
def get_transactions_sum(date, transaction_lines):
    return_val = 0
    for fields in transaction_lines:
        try:
            txn_date = datetime.strptime(fields[0], "%b-%d-%Y")
            if ("TAX" in fields[1] or "REINVEST" in fields[1]) and "FIDELITY" in fields[2]:
                continue
            if txn_date == date:
                return_val += float(fields[4].replace("$", ""))
        except ValueError:
            continue
    return return_val

# TODO
def account_peak_balance(opening_cash_res, transaction_summary_list):

    cash_balance = opening_cash_res
    max_so_far = cash_balance
    temp_date = datetime(CURRENT_TAX_YEAR-1, 1, 1)
    max_date = temp_date
    max_cash_balance = cash_balance
    max_stock_balance = 0
    while temp_date < datetime(CURRENT_TAX_YEAR, 1, 1):
        cash_balance += get_transactions_sum(temp_date, transaction_summary_list)
        stock_balance = sum([unit["qty"] for unit in A3_UNITS_LIST if (unit["date_sold"] is None or unit["date_sold"] > temp_date) and unit["date_acquired"] < temp_date])*get_orcl_peak_date_and_price(temp_date, temp_date)[1]
        if cash_balance + stock_balance > max_so_far:
            max_so_far = cash_balance + stock_balance
            max_date = temp_date
            max_cash_balance = cash_balance
            max_stock_balance = stock_balance
        temp_date = temp_date + timedelta(days=1)
    global ACCOUNT_PEAK_BALANCE_INR, ACCOUNT_CLOSING_BALANCE_INR
    ACCOUNT_PEAK_BALANCE_INR = round(max_so_far*fetch_last_available_tt_buy(max_date))
    print(f"Account peak balance was on {str(max_date)} with cash balance ${max_cash_balance} and stock balance ${max_stock_balance}")
    temp_date = max_date
    ACCOUNT_CLOSING_BALANCE_INR = round((cash_balance*fetch_last_available_tt_buy(datetime(CURRENT_TAX_YEAR-1, 12, 31)) + sum([unit["closing_price"] for unit in A3_UNITS_LIST])))

# TODO
def fetch_orcl_prices():
    url = f"https://finance.yahoo.com/quote/ORCL/history/?period1={int(datetime(CURRENT_TAX_YEAR-2, 12, 29).timestamp())}&period2={int(datetime(CURRENT_TAX_YEAR, 1, 1).timestamp())}"
    # 1. Create an Options object
    chrome_options = Options()
    print("Loading webpage for fetching ORCL prices for last year. Please wait...", end='', flush=True)
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--window-size=1920,1080")
    driver = webdriver.Chrome(options=chrome_options)
    driver.get(url)

    contents = driver.page_source
    print("\rDone.", end='', flush=True)
    print(" "*100, flush=True)
    driver.quit()
    soup = BeautifulSoup(contents, 'html.parser')
    value_rows = soup.find_all('tr')
    for row in value_rows:
        td_tags = row.find_all('td')
        if len(td_tags) == 7:
            global ORCL_CY_CLOSING_PRICE
            ORCL_PEAK_PRICE_MAP[datetime.strptime(td_tags[0].text, "%b %d, %Y")] = float(td_tags[2].text)
            if datetime.strptime(td_tags[0].text, "%b %d, %Y") == datetime(CURRENT_TAX_YEAR-1, 12, 31):
                ORCL_CY_CLOSING_PRICE = float(td_tags[5].text)

def generate_a2_csv(output_dir):
    a2_file = open(output_dir + "/A2_details_orcl_" + str(CURRENT_TAX_YEAR-1) + ".csv", "w")
    a2_file.write("\"Country/Region name\",\"Country Name and Code\",\"Name of financial institution\",\"Address of financial institution\",\"ZIP Code\",\"Account Number\",\"Status\",\"Account opening date\",\"Peak Balance During the Period\",\"Closing balance\",\"Nature of Amount\",\"Amount\",\n")
    a2_file.write(f"UNITED STATES OF AMERICA,2,Fidelity Stock Plan Services,245 Summer Street Boston MA,02210,{PARTICIPANT_NUMBER},OWNER,{ACCOUNT_OPENING_DATE},{round(ACCOUNT_PEAK_BALANCE_INR)},{round(ACCOUNT_CLOSING_BALANCE_INR)},")
    if LAST_CY_ORCL_DIVIDENDS_LIST:
        a2_file.write(f"Dividend,{round(sum([dividend["amount_inr"] for dividend in LAST_CY_ORCL_DIVIDENDS_LIST]) + LAST_CY_FIDELITY_INTEREST)},\n")
    else: a2_file.write(",,\n")
    if TOTAL_CY_CAPITAL_GAINS > 0:
        a2_file.write(f"UNITED STATES OF AMERICA,2,Fidelity Stock Plan Services,245 Summer Street Boston MA,02210,{PARTICIPANT_NUMBER},OWNER,{ACCOUNT_OPENING_DATE},{round(ACCOUNT_PEAK_BALANCE_INR)},{round(ACCOUNT_CLOSING_BALANCE_INR)},Proceeds from sale,{round(TOTAL_CY_CAPITAL_GAINS)},\n")
    a2_file.close()
    print("A2 CSV file generated")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--files-dir", help="Path to directory containing relevant files (Txn summary CSVs, open lots and closed lots CSV)", required=True)
    parser.add_argument("-b", "--opening-cash-balance", help="Opening cash reserve balance for last CY in USD", required=True, type=float)
    parser.add_argument("-ao", "--account-open-date", help="Account opening date in numerical YYYY-MM-DD format", required=True)
    parser.add_argument("-p", "--participant-account-number", help="Fidelity participant account number", required=True)
    parser.add_argument("-o", "--output-dir", help="Path to directory where Output files should be generated", required=True)
    parser.add_argument("-fy", "--financial-year", help="Financial year running for (ex. 2024-2025)")
    args = parser.parse_args()

    if args.financial_year is None:
        CURRENT_TAX_YEAR = datetime.now().year
    else:
        CURRENT_TAX_YEAR = int(args.financial_year.split("-")[1])

    init(args)
    init_tt_buy()
    parse_transaction_summary_dividends(LAST_CY_TXN_LIST, CURRENT_CY_TXN_LIST, args.output_dir)
    parse_shares(OPEN_LOTS_FILE, CLOSED_LOTS_FILE, args.output_dir)
    populate_dividends_for_a3()
    generate_a3_csv(args.output_dir)
    account_peak_balance(ACCOUNT_STARTING_CASH_RESERVE_BALANCE_USD, LAST_CY_TXN_LIST)
    generate_a2_csv(args.output_dir)