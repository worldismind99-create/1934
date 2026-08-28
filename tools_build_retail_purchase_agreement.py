# -*- coding: utf-8 -*-
"""Blank RETAIL PURCHASE AGREEMENT form (Excel) - layout mirrors the supplied paper form."""
import openpyxl
from openpyxl.styles import Font, Alignment, Border, Side, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.page import PageMargins

OUT = "/home/user/1934/Retail_Purchase_Agreement_Blank.xlsx"

wb = openpyxl.Workbook()
ws = wb.active
ws.title = "Retail Purchase Agreement"

FONT = "Arial"
thin = Side(style="thin", color="000000")
hair = Side(style="hair", color="000000")
box = Border(left=thin, right=thin, top=thin, bottom=thin)
underline = Border(bottom=thin)

def f(size=7, bold=False, italic=False, underline_=None):
    return Font(name=FONT, size=size, bold=bold, italic=italic, underline=underline_)

def put(cell, value=None, size=7, bold=False, italic=False, align="left",
        valign="center", wrap=False, merge=None, border=None, fmt=None, indent=0):
    if merge:
        ws.merge_cells(merge)
    c = ws[cell]
    if value is not None:
        c.value = value
    c.font = f(size, bold, italic)
    c.alignment = Alignment(horizontal=align, vertical=valign, wrap_text=wrap, indent=indent)
    if fmt:
        c.number_format = fmt
    if border:
        rng = merge if merge else cell
        target = ws[rng]
        if not isinstance(target, tuple):
            target = ((target,),)
        for row in target:
            for cc in row:
                cc.border = border
    return c

def outline(rng, side=thin):
    """Draw a box around a rectangular range."""
    cells = ws[rng]
    if not isinstance(cells, tuple):
        cells = ((cells,),)
    if cells and not isinstance(cells[0], tuple):
        cells = (cells,)
    nrows = len(cells)
    ncols = len(cells[0])
    for i, row in enumerate(cells):
        for j, c in enumerate(row):
            b = c.border
            c.border = Border(
                left=side if j == 0 else b.left,
                right=side if j == ncols - 1 else b.right,
                top=side if i == 0 else b.top,
                bottom=side if i == nrows - 1 else b.bottom,
            )

# ---------------------------------------------------------------- columns
widths = {"A": 2.0, "B": 11.0, "C": 11.0, "D": 11.0, "E": 11.0, "F": 11.0,
          "G": 11.0, "H": 11.0, "I": 11.0, "J": 1.5, "K": 28.0, "L": 13.0, "M": 2.0}
for col, w in widths.items():
    ws.column_dimensions[col].width = w

MONEY = '$#,##0.00;($#,##0.00);"-"'

# ---------------------------------------------------------------- header (rows 1-4)
put("B1", "DOGGETT FORD", size=10, bold=True, merge="B1:D1")
put("B2", "9225 NORTH FREEWAY", size=7, merge="B2:D2")
put("B3", "HOUSTON, TX 77037", size=7, merge="B3:D3")
put("B4", "281-878-4200", size=7, merge="B4:D4")

put("E1", "RETAIL PURCHASE AGREEMENT", size=13, bold=True, align="center", merge="E1:I2")

put("K1", "CUST#", size=7, align="right")
put("L1", None, size=8, border=underline)
put("K2", "Deal Number:", size=7, align="right")
put("L2", None, size=8, border=underline)

for r in (1, 2, 3, 4):
    ws.row_dimensions[r].height = 14

# ---------------------------------------------------------------- parties (rows 6-9)
ws.row_dimensions[5].height = 5
party_rows = [
    (6,  "Purchaser's Name(s):", "Date:"),
    (7,  "Address(es):",         "County:"),
    (8,  "Telephone (1):",       "Telephone (2):"),
    (9,  "Email (1):",           "Email (2):"),
]
for r, left_lbl, right_lbl in party_rows:
    ws.row_dimensions[r].height = 16
    put("B%d" % r, left_lbl, size=7, merge="B%d:C%d" % (r, r))
    put("D%d" % r, None, size=8, merge="D%d:I%d" % (r, r), border=underline)
    put("K%d" % r, right_lbl, size=7, align="right")
    put("L%d" % r, None, size=8, border=underline)

# ---------------------------------------------------------------- odometer notice (row 10)
put("B10",
    "The Odometer Reading for the Vehicle You are purchasing is accurate unless indicated otherwise. "
    "Please refer to the Odometer Mileage Statement for full disclosure.",
    size=6, wrap=True, valign="center", merge="B10:L10")
ws.row_dimensions[10].height = 16
ws.row_dimensions[11].height = 4

# ---------------------------------------------------------------- vehicle table (rows 12-16)
put("B12", "YEAR", size=6, bold=True, align="center")
put("C12", "MAKE", size=6, bold=True, align="center")
put("D12", "MODEL", size=6, bold=True, align="center", merge="D12:E12")
put("F12", "COLOR", size=6, bold=True, align="center", merge="F12:G12")
put("H12", "STOCK NO.", size=6, bold=True, align="center", merge="H12:I12")
ws.row_dimensions[12].height = 12

for rng in ("B13:B13", "C13:C13", "D13:E13", "F13:G13", "H13:I13"):
    tl = rng.split(":")[0]
    put(tl, None, size=8, align="center", merge=None if rng.split(":")[0] == rng.split(":")[1] else rng)
    outline(rng)
ws.row_dimensions[13].height = 16

put("B14", "VIN", size=6, bold=True, align="center", merge="B14:C14")
put("D14", "(Vehicle)", size=6, italic=True, align="center")
put("E14", "ODOMETER READING", size=6, bold=True, align="center")
put("F14", "☐ Not Accurate", size=6, align="center")
put("G14", "SALESPERSON", size=6, bold=True, align="center", merge="G14:I14")
ws.row_dimensions[14].height = 12

for rng in ("B15:C15", "E15:E15", "G15:I15"):
    tl = rng.split(":")[0]
    put(tl, None, size=8, align="center", merge=None if rng.split(":")[0] == rng.split(":")[1] else rng)
    outline(rng)
ws.row_dimensions[15].height = 16

put("B16", "THE VEHICLE IS:      ☐ NEW      ☐ USED", size=6.5, bold=True, merge="B16:D16")
put("E16", "PRIOR USE DISCLOSURE:   ☐ DEMONSTRATOR   ☐ PREVIOUSLY LEASED   "
           "☐ EXECUTIVE VEHICLE   ☐ RENTAL   ☐ OTHER",
    size=6.5, bold=True, merge="E16:I16")
outline("B16:I16")
ws.row_dimensions[16].height = 14

# ---------------------------------------------------------------- LEFT column blocks
WARRANTY = ("We are selling this Vehicle to You AS-IS and We expressly disclaim all warranties, express and "
            "implied, including any implied warranties of merchantability and fitness for a particular purpose, "
            "unless the box beside \"Used Vehicle Limited Warranty Applies\" is marked below or We enter into a "
            "service contract with You at the time of, or within 90 days of, the date of this transaction. All "
            "warranties, if any, by a manufacturer or supplier other than Our Dealership are theirs, not Ours, and "
            "no manufacturer or supplier shall be liable for performance under such warranties. We neither assume "
            "nor authorize any other person to assume for Us any liability in connection with the sale of the "
            "Vehicle and related goods and services.")

DISCLOSURE = ("You see on the window form for this Vehicle is part of this contract. Information on the window form "
              "overrides any contrary provisions in the contract of sale.  Traducción española: Guía "
              "para compradores de vehículos usados. La información que ve en el formulario de la "
              "ventanilla para este vehículo forma parte del presente contrato. La información del "
              "formulario de la ventanilla deja sin efecto toda disposición en contrario contenida en el "
              "contrato de venta.")

UVLW = ("☐ Used Vehicle Limited Warranty Applies:  We are providing a Used Vehicle Limited Warranty in "
        "connection with this transaction. Any implied warranties apply for the duration of the Limited Warranty.")

put("B17", "WARRANTY STATEMENT", size=8, bold=True, align="center", merge="B17:I17")
outline("B17:I17")
ws.row_dimensions[17].height = 13

put("B18", WARRANTY, size=6, wrap=True, valign="top", merge="B18:I23")
outline("B18:I23")
for r in range(18, 24):
    ws.row_dimensions[r].height = 16

put("B24", "CONTRACTUAL DISCLOSURE STATEMENT (USED VEHICLES ONLY) The information",
    size=6.5, bold=True, merge="B24:I24")
put("B25", DISCLOSURE, size=6, wrap=True, valign="top", merge="B25:I28")
outline("B24:I28")
ws.row_dimensions[24].height = 12
for r in range(25, 29):
    ws.row_dimensions[r].height = 16

put("B29", UVLW, size=6, wrap=True, valign="top", merge="B29:I30")
outline("B29:I30")
for r in (29, 30):
    ws.row_dimensions[r].height = 15

# --- trade vehicle information (rows 31-41)
put("B31", "TRADE VEHICLE INFORMATION", size=8, bold=True, align="center", merge="B31:I31")
outline("B31:I31")
ws.row_dimensions[31].height = 13

def trade_block(r0, label):
    put("B%d" % r0, "Lienholder Name:", size=6)
    put("C%d" % r0, None, size=7, merge="C%d:I%d" % (r0, r0), border=underline)
    put("B%d" % (r0 + 1), "Lienholder Address:", size=6)
    put("C%d" % (r0 + 1), None, size=7, merge="C%d:I%d" % (r0 + 1, r0 + 1), border=underline)

    r = r0 + 2
    for col, lbl in (("B", "Year:"), ("D", "Make:"), ("F", "Model:"), ("H", "Color:")):
        put("%s%d" % (col, r), lbl, size=6)
    for col in ("C", "E", "G", "I"):
        put("%s%d" % (col, r), None, size=7, border=underline)

    r = r0 + 3
    put("B%d" % r, "VIN:", size=6)
    put("C%d" % r, None, size=7, merge="C%d:D%d" % (r, r), border=underline)
    put("E%d" % r, label, size=6, italic=True, align="center")
    put("F%d" % r, "Odometer Reading:", size=6)
    put("G%d" % r, None, size=7, border=underline)
    put("H%d" % r, "☐ Not Accurate", size=6, merge="H%d:I%d" % (r, r))

    r = r0 + 4
    put("B%d" % r, "Trade Allowance:", size=6)
    put("C%d" % r, None, size=7, fmt=MONEY, border=underline)
    put("D%d" % r, "Balance Owed to Lienholder:", size=6, merge="D%d:E%d" % (r, r))
    put("F%d" % r, None, size=7, fmt=MONEY, merge="F%d:G%d" % (r, r), border=underline)

    for rr in range(r0, r0 + 5):
        ws.row_dimensions[rr].height = 14

trade_block(32, "(Trade Vehicle 1)")
trade_block(37, "(Trade Vehicle 2)")
outline("B32:I41")

# --- other material understandings (rows 42-45)
put("B42", "OTHER MATERIAL UNDERSTANDINGS AND INTEGRATED DOCUMENTS",
    size=8, bold=True, align="center", merge="B42:I42")
outline("B42:I42")
ws.row_dimensions[42].height = 13

put("B43", "☐  PLEASE SEE THE DELIVERY CONFIRMATION", size=6.5, merge="B43:I43")
put("B44", "☐  PLEASE SEE THE CONDITIONAL DELIVERY AGREEMENT", size=6.5, merge="B44:I44")
put("B45", "Prospective Lienholder:", size=6.5, merge="B45:C45")
put("D45", None, size=7, merge="D45:I45", border=underline)
outline("B43:I45")
for r in (43, 44, 45):
    ws.row_dimensions[r].height = 14

# --- statutory notices (rows 46-51)
INV_TAX = ("Dealer's Inventory Tax: The Dealer's Inventory Tax charge is intended to reimburse the Dealer for ad "
           "valorem taxes on its motor vehicle inventory. The charge, which is paid by the Dealer to the county tax "
           "assessor-collector, is not a tax imposed on a consumer by the government, and is not required to be "
           "charged to the consumer.")
DOC_FEE = ("*Documentary Fee: A documentary fee is not an official fee. A documentary fee is not required by law, "
           "but may be charged to buyers for handling documents relating to the sale. A documentary fee may not "
           "exceed a reasonable amount agreed to by the parties. This notice is required by law.  "
           "Traducción española: Vea Párrafo 13.")

put("B46", INV_TAX, size=6, bold=True, wrap=True, valign="top", merge="B46:I48")
put("B49", DOC_FEE, size=6, bold=True, wrap=True, valign="top", merge="B49:I51")
for r in range(46, 52):
    ws.row_dimensions[r].height = 15

# ---------------------------------------------------------------- RIGHT column: pricing
R_BASE = 17
R_OPT_HDR = 18
R_OPT_FIRST, R_OPT_LAST = 19, 30
R_TOTAL_SELL = 31
R_TRADE_ALLOW = 32
R_SUBTOTAL = 33
R_FEE_FIRST, R_FEE_LAST = 34, 43
R_TOTAL_DUE = 45
R_DOWN = 46
R_REBATES = 47
R_CASH_DUE = 48
R_FINANCED = 50

def price_row(r, label, bold=False, formula=None, shade=False):
    put("K%d" % r, label, size=7, bold=bold)
    c = put("L%d" % r, formula, size=7, bold=bold, align="right", fmt=MONEY)
    for cell in ("K%d" % r, "L%d" % r):
        ws[cell].border = box
    if shade:
        fill = PatternFill("solid", fgColor="EFEFEF")
        ws["K%d" % r].fill = fill
        ws["L%d" % r].fill = fill
    ws.row_dimensions[r].height = 14
    return c

price_row(R_BASE, "Base Selling Price", bold=True)
put("K%d" % R_OPT_HDR, "Optional Items:", size=7, italic=True)
put("L%d" % R_OPT_HDR, None, size=7)
for cell in ("K%d" % R_OPT_HDR, "L%d" % R_OPT_HDR):
    ws[cell].border = box
ws.row_dimensions[R_OPT_HDR].height = 14

for r in range(R_OPT_FIRST, R_OPT_LAST + 1):
    price_row(r, None)

price_row(R_TOTAL_SELL, "TOTAL SELLING PRICE", bold=True, shade=True,
          formula="=L%d+SUM(L%d:L%d)" % (R_BASE, R_OPT_FIRST, R_OPT_LAST))
price_row(R_TRADE_ALLOW, "LESS: TRADE IN ALLOWANCE")
price_row(R_SUBTOTAL, "SUBTOTAL", bold=True, shade=True,
          formula="=L%d-L%d" % (R_TOTAL_SELL, R_TRADE_ALLOW))

fees = ["SALES TAX", "DEALER'S INVENTORY TAX", "DOCUMENTARY FEE*", "STATE INSPECTION FEE",
        "DEPUTY SERVICE FEE", "LICENSE FEE", "TITLE FEE", "City Road & Bridge",
        "Processing Fee", "Govt Vehicle Inspection Replacement Fee"]
for i, name in enumerate(fees):
    price_row(R_FEE_FIRST + i, name)

ws.row_dimensions[44].height = 5
price_row(R_TOTAL_DUE, "TOTAL DUE", bold=True, shade=True,
          formula="=L%d+SUM(L%d:L%d)" % (R_SUBTOTAL, R_FEE_FIRST, R_FEE_LAST))
price_row(R_DOWN, "DOWN PAYMENT")
price_row(R_REBATES, "REBATES")
price_row(R_CASH_DUE, "LESS CASH DUE AT DELIVERY")
ws.row_dimensions[49].height = 5
price_row(R_FINANCED, "AMOUNT TO BE FINANCED", bold=True, shade=True,
          formula="=L%d-L%d-L%d-L%d" % (R_TOTAL_DUE, R_DOWN, R_REBATES, R_CASH_DUE))

# ---------------------------------------------------------------- approvals / consent
medium = Side(style="medium", color="000000")
ws.row_dimensions[52].height = 8
for col in "BCDEFGHIJKL":
    ws["%s53" % col].border = Border(top=medium)

ws.row_dimensions[53].height = 22
put("B53", "Customer Approval:", size=8, bold=True, valign="bottom", merge="B53:C53")
put("D53", None, size=9, valign="bottom", merge="D53:F53")
put("G53", "Management Approval:", size=8, bold=True, valign="bottom", merge="G53:H53")
put("I53", None, size=9, valign="bottom", merge="I53:L53")
for col in ("D", "E", "F", "I", "K", "L"):
    b = ws["%s53" % col].border
    ws["%s53" % col].border = Border(top=b.top, bottom=thin)
ws["J53"].border = Border(top=medium, bottom=thin)

CONSENT = ("By signing this authorization form, you certify that the above personal information is correct and "
           "accurate, and authorize the release of credit and employment information. By signing above, I provide "
           "to the dealership and its affiliates consent to communicate with me about my vehicle or any future "
           "vehicles using electronic verbal and written communications including but not limited to email, text "
           "messaging, SMS, phone calls and direct mail. Terms and conditions subject to credit approval. For "
           "information only. This is not an offer or contract for sale.")
put("B54", CONSENT, size=5.5, wrap=True, valign="top", merge="B54:L56")
for r in (54, 55, 56):
    ws.row_dimensions[r].height = 12

# ---------------------------------------------------------------- footer
ws.row_dimensions[57].height = 8
put("B58", "IMPORTANT TERMS AND CONDITIONS FOLLOW", size=8, bold=True, merge="B58:F58")
put("K58", "Page 1 of 3", size=7, align="right", merge="K58:L58")
ws.row_dimensions[58].height = 14

# ---------------------------------------------------------------- page setup
ws.print_area = "A1:M58"
ws.page_setup.orientation = "portrait"
ws.page_setup.paperSize = ws.PAPERSIZE_LETTER
ws.page_setup.fitToWidth = 1
ws.page_setup.fitToHeight = 1
ws.sheet_properties.pageSetUpPr.fitToPage = True
ws.page_margins = PageMargins(left=0.3, right=0.3, top=0.3, bottom=0.3)
ws.sheet_view.showGridLines = False

# ================================================================ sheet 2: how to use
gs = wb.create_sheet("使い方 (Instructions)")
gs.column_dimensions["A"].width = 26
gs.column_dimensions["B"].width = 62
gs.column_dimensions["C"].width = 22

def g(row, a, b, c=None, bold=False, size=10):
    gs.cell(row=row, column=1, value=a).font = Font(name=FONT, size=size, bold=bold)
    gs.cell(row=row, column=2, value=b).font = Font(name=FONT, size=size, bold=bold)
    gs.cell(row=row, column=2).alignment = Alignment(wrap_text=True, vertical="top")
    if c is not None:
        gs.cell(row=row, column=3, value=c).font = Font(name=FONT, size=size, bold=bold)

g(1, "RETAIL PURCHASE AGREEMENT", "空白フォーム / Blank form - 記入ガイド", bold=True, size=12)
g(3, "入力欄 (Input)", "説明", "記入例 (Example)", bold=True)
rows = [
    ("L1 / L2", "CUST# / Deal Number", "408132 / 343179"),
    ("D6:I6 / L6", "Purchaser's Name(s) / Date", "JOHN DOE / 08/06/2026"),
    ("D7:I7 / L7", "Address(es) / County", "541 RUBY RIVER DR / MADISON"),
    ("D8:I8 / L8", "Telephone (1) / Telephone (2)", "555-0100 / N/A"),
    ("D9:I9 / L9", "Email (1) / Email (2)", "sample@example.com"),
    ("B13:I13", "YEAR / MAKE / MODEL / COLOR / STOCK NO.", "2026 / FORD / BRONCO"),
    ("B15:I15", "VIN / ODOMETER READING / SALESPERSON", "1FMEE4DP3TLB00730 / 11"),
    ("B16:I16", "New・Used、Prior Use Disclosure のチェック欄 (☐ を ☑ に置換)", "☑ NEW"),
    ("C32:I41", "TRADE VEHICLE INFORMATION (下取車1・2)", "N/A"),
    ("D45", "Prospective Lienholder", "N/A"),
    ("L17", "Base Selling Price", "$52,810.00"),
    ("K19:L30", "Optional Items - 品名を K 列、金額を L 列に入力", "ALARM-AT / $305.00"),
    ("L32", "LESS: TRADE IN ALLOWANCE", "$0.00"),
    ("L34:L43", "各種税金・手数料 (SALES TAX 〜 Govt Vehicle Inspection Replacement Fee)", "$225.00"),
    ("L46 / L47 / L48", "DOWN PAYMENT / REBATES / LESS CASH DUE AT DELIVERY", "$0.00 / $2,000.00 / $0.00"),
    ("D53 / I53", "Customer Approval / Management Approval (署名欄)", "署名"),
]
r = 4
for a, b, c in rows:
    g(r, a, b, c)
    r += 1

r += 1
g(r, "自動計算 (編集しないこと)", "計算式", "", bold=True)
r += 1
auto = [
    ("L31  TOTAL SELLING PRICE", "= L17 + SUM(L19:L30)"),
    ("L33  SUBTOTAL", "= L31 - L32"),
    ("L45  TOTAL DUE", "= L33 + SUM(L34:L43)"),
    ("L50  AMOUNT TO BE FINANCED", "= L45 - L46 - L47 - L48"),
]
for a, b in auto:
    g(r, a, b, "")
    r += 1

r += 1
g(r, "備考", "・金額欄の書式は $#,##0.00 (USD)。マイナスは ($#,##0.00)、空欄は「-」と表示されます。", "")
r += 1
g(r, "", "・グレー網掛けの行は数式です。上書きすると再計算されません。", "")
r += 1
g(r, "", "・ディーラー名・住所 (B1:D4) は必要に応じて書き換えてください。", "")
r += 1
g(r, "", "・印刷設定: レター / 縦 / 1ページに収める。", "")

wb.save(OUT)
print("saved", OUT)
