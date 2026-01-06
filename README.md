# CryTR2 - Cry Tears with ITR2

A script to instantly generate tears by calculating your capital gains and dividends for Oracle Fidelity foreign assets. Also generates table A2 and table A3 CSVs for Schedule FA so that the government won't imprison you while you are sitting in your corner crying.
This script only makes Oracle employees or people with Oracle stocks in Fidelity cry. If you are from another organization, feel free to be inspired and modify the script for your usecase or something... you do you bruh!

### Usage
Hydrate yourself well so that there is enough water in your body for the tear glands. Then login to your Fidelity account and do the following:
1. Click on Stock plan account
2. Click on "View shares" next to the ORACLE CORP stock units
3. For both "Currently Held" and "Previously Held" shares, click on Export to download a CSV containing the shares details
4. Open the "Previously held" CSV (the filename will contain "closed lots") and for all the units displayed, add a final column indicating
   if the share was from RS (for RSU) or SP (for ESPP). This detail can be found on the UI but will be missing in the CSV. The open lots file
   will have this column in the end already so you can put in the info in closed lots file in the same way as a final column in the end separated
   by a comma
5. Click on Activity tab and select a date range for your previous "Calendar" year and current "Calendar" year and click on Export for both
6. Open both the above downloaded "Transaction history" files and verify that the transaction dates are only for the respective Calendar years.
   Fidelity is weird and sometimes includes transactions from the previous year and sometimes excludes transactions from that year.
7. Copy all 4 files (open lots, closed lots, and 2 transaction history files) into some directory (say dir1)
8. Create virtualenv if you want to and install the python3 dependencies in requirements.txt
9. Run the script using `python3 cry.py -f /path/to/dir1 -b <fidelity cash reserve balance at start of previous calendar year> -ao <fidelity account opening date> -p <fidelity participant ID> -o /path/to/output/dir -fy <financial year>`
10. The output files will be generated in /path/to/output/dir
11. Watch the tears flow as you fill your ITR