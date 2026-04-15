from __future__ import annotations

from io import BytesIO
from textwrap import wrap

from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas


def _format_currency(amount):
    if amount is None:
        return "-"
    formatted = f"{amount:,.2f}"
    formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
    return f"${formatted}"


def _format_liters(amount):
    if amount is None:
        return "-"
    return f"{amount:,.2f} L".replace(",", "X").replace(".", ",").replace("X", ".")


def _format_datetime(value):
    if value is None:
        return "-"
    local_value = timezone.localtime(value)
    return local_value.strftime("%d/%m/%Y %H:%M")


def _format_date(value):
    if value is None:
        return "-"
    local_value = timezone.localtime(value)
    return local_value.strftime("%d/%m/%Y")


def _get_user_label(user):
    if user is None:
        return "-"
    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return full_name or "-"


def build_fuel_load_remito_pdf(fuel_load):
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    operation_amount = (
        fuel_load.final_amount
        if fuel_load.final_amount is not None
        else fuel_load.initial_amount
    )
    station = fuel_load.station
    account = fuel_load.account
    user = account.user if account else None
    display_in_liters = (account.display_type == "litros") if account else False
    fuel_type_name = fuel_load.fuel_type.name if fuel_load.fuel_type else "-"

    margin = 12 * mm
    content_left = margin
    content_right = width - margin
    content_top = height - margin
    content_bottom = margin
    content_width = content_right - content_left
    content_height = content_top - content_bottom

    header_h = 45 * mm
    section1_h = 18 * mm
    section2_h = 8 * mm
    section3_h = 8 * mm
    observations_h = 45 * mm
    bottom_bar_h = 8 * mm
    table_h = content_height - (
        header_h + section1_h + section2_h + section3_h + observations_h + bottom_bar_h
    )

    if table_h < 60 * mm:
        table_h = 60 * mm
        observations_h = content_height - (
            header_h + section1_h + section2_h + section3_h + bottom_bar_h + table_h
        )

    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(1)
    pdf.rect(
        content_left, content_bottom, content_width, content_height, stroke=1, fill=0
    )

    header_top = content_top
    header_bottom = header_top - header_h
    pdf.rect(content_left, header_bottom, content_width, header_h, stroke=1, fill=0)

    left_w = content_width * 0.62
    left_x = content_left
    right_x = content_left + left_w
    right_w = content_width - left_w
    pdf.line(right_x, header_bottom, right_x, header_top)

    pdf.setFillColor(colors.HexColor("#1B2F5B"))
    pdf.setFont("Helvetica-Bold", 32)
    pdf.drawString(left_x + 6 * mm, header_top - 18 * mm, "WICO")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(left_x + 7 * mm, header_top - 27 * mm, "COMBUSTIBLES")

    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(left_x + 7 * mm, header_top - 33 * mm, "COMBUSTIBLES ITALO")
    pdf.drawString(left_x + 7 * mm, header_top - 37 * mm, "ARGENTINO S.A.")
    pdf.drawString(
        left_x + 7 * mm, header_top - 41 * mm, "I.V.A. RESPONSABLE INSCRIPTO"
    )

    r_box_size = 12 * mm
    r_box_x = left_x + left_w - 28 * mm
    r_box_y = header_top - 18 * mm
    pdf.setLineWidth(1)
    pdf.rect(r_box_x, r_box_y, r_box_size, r_box_size, stroke=1, fill=0)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(r_box_x + r_box_size / 2, r_box_y + 3.5 * mm, "R")

    pdf.setFont("Helvetica", 6.2)
    pdf.drawCentredString(r_box_x + r_box_size / 2, r_box_y - 2 * mm, "CODIGO")
    pdf.drawCentredString(r_box_x + r_box_size / 2, r_box_y - 5.5 * mm, "Documento NO")
    pdf.drawCentredString(r_box_x + r_box_size / 2, r_box_y - 8.5 * mm, "valido como")
    pdf.drawCentredString(r_box_x + r_box_size / 2, r_box_y - 11.5 * mm, "FACTURA")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(right_x + 6 * mm, header_top - 12 * mm, "REMITO")
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(
        right_x + right_w - 6 * mm, header_top - 12 * mm, f"N {fuel_load.id}"
    )

    date_box_x = right_x + 6 * mm
    date_box_y = header_top - 26 * mm
    date_box_w = right_w - 12 * mm
    date_box_h = 8 * mm
    pdf.roundRect(date_box_x, date_box_y, date_box_w, date_box_h, 2, stroke=1, fill=0)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(date_box_x + 2 * mm, date_box_y + 2 * mm, "FECHA")
    pdf.drawRightString(
        date_box_x + date_box_w - 2 * mm,
        date_box_y + 2 * mm,
        _format_date(fuel_load.timestamp_finished),
    )

    pdf.setFont("Helvetica", 8)
    pdf.drawString(right_x + 6 * mm, header_top - 34 * mm, "CUIT:")
    pdf.drawString(right_x + 25 * mm, header_top - 34 * mm, "30-71611995-1")
    pdf.drawString(right_x + 6 * mm, header_top - 39 * mm, "INGR. BRUTOS:")
    pdf.drawString(right_x + 35 * mm, header_top - 39 * mm, "30-71611995-1")
    pdf.drawString(right_x + 6 * mm, header_top - 44 * mm, "INICIO ACT.:")
    pdf.drawString(right_x + 35 * mm, header_top - 44 * mm, "25/07/2018")

    section1_top = header_bottom
    section1_bottom = section1_top - section1_h
    pdf.rect(content_left, section1_bottom, content_width, section1_h, stroke=1, fill=0)

    label_x = content_left + 4 * mm
    row1_y = section1_top - 6 * mm
    pdf.setFont("Helvetica", 9)
    pdf.drawString(label_x, row1_y, "Senor/es:")
    pdf.line(
        label_x + 18 * mm, row1_y - 1 * mm, content_right - 4 * mm, row1_y - 1 * mm
    )
    pdf.drawString(
        label_x + 20 * mm,
        row1_y,
        _get_user_label(user),
    )

    row2_y = section1_top - 13 * mm
    pdf.drawString(label_x, row2_y, "DNI:")
    pdf.line(label_x + 10 * mm, row2_y - 1 * mm, label_x + 65 * mm, row2_y - 1 * mm)
    pdf.drawString(label_x + 12 * mm, row2_y, user.dni if user and user.dni else "-")

    org_label_x = label_x + 72 * mm
    pdf.drawString(org_label_x, row2_y, "Organismo:")
    pdf.line(
        org_label_x + 24 * mm, row2_y - 1 * mm, content_right - 4 * mm, row2_y - 1 * mm
    )
    pdf.drawString(org_label_x + 26 * mm, row2_y, "-")

    section2_top = section1_bottom
    section2_bottom = section2_top - section2_h
    pdf.rect(content_left, section2_bottom, content_width, section2_h, stroke=1, fill=0)

    plate_y = section2_top - 5.5 * mm
    pdf.drawString(label_x, plate_y, "Patente de Vehiculo:")
    pdf.line(
        label_x + 36 * mm, plate_y - 1 * mm, content_right - 4 * mm, plate_y - 1 * mm
    )
    pdf.drawString(
        label_x + 38 * mm,
        plate_y,
        fuel_load.plate.plate_number if fuel_load.plate else "-",
    )

    section3_top = section2_bottom
    section3_bottom = section3_top - section3_h
    pdf.rect(content_left, section3_bottom, content_width, section3_h, stroke=1, fill=0)

    iva_y = section3_top - 5.5 * mm
    pdf.drawString(label_x, iva_y, "I.V.A.")

    def draw_checkbox(x, y, label, checked=False):
        box_size = 3.5 * mm
        pdf.rect(x, y - 2 * mm, box_size, box_size, stroke=1, fill=0)
        if checked:
            pdf.setFont("Helvetica-Bold", 8)
            pdf.drawString(x + 0.7 * mm, y - 1 * mm, "X")
            pdf.setFont("Helvetica", 8)
        pdf.drawString(x + 5 * mm, y - 0.5 * mm, label)

    checkbox_y = iva_y
    checkbox_x = label_x + 18 * mm
    pdf.setFont("Helvetica", 8)
    draw_checkbox(checkbox_x, checkbox_y, "Resp. Inscripto", checked=False)
    draw_checkbox(checkbox_x + 35 * mm, checkbox_y, "Monotributo", checked=False)
    draw_checkbox(checkbox_x + 65 * mm, checkbox_y, "Cons. Final", checked=True)
    draw_checkbox(checkbox_x + 92 * mm, checkbox_y, "Exento", checked=False)

    table_top = section3_bottom
    table_bottom = table_top - table_h
    pdf.rect(content_left, table_bottom, content_width, table_h, stroke=1, fill=0)

    header_row_h = 7 * mm
    pdf.setFillColor(colors.HexColor("#1B2F5B"))
    pdf.rect(
        content_left,
        table_top - header_row_h,
        content_width,
        header_row_h,
        stroke=0,
        fill=1,
    )
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 9)

    val_col_w = 25 * mm
    fuel_col_w = 30 * mm
    desc_col_x = content_left + val_col_w + fuel_col_w
    desc_col_w = content_width - val_col_w - fuel_col_w
    val_col_header = "CANTIDAD" if display_in_liters else "MONTO"
    pdf.drawCentredString(
        content_left + val_col_w / 2, table_top - 5 * mm, val_col_header
    )
    pdf.drawCentredString(
        content_left + val_col_w + fuel_col_w / 2, table_top - 5 * mm, "COMBUSTIBLE"
    )
    pdf.drawCentredString(
        desc_col_x + desc_col_w / 2, table_top - 5 * mm, "DESCRIPCION"
    )

    pdf.setFillColor(colors.black)
    pdf.setLineWidth(0.5)
    pdf.line(
        content_left + val_col_w, table_bottom, content_left + val_col_w, table_top
    )
    pdf.line(desc_col_x, table_bottom, desc_col_x, table_top)

    row_count = 8
    row_h = (table_h - header_row_h) / row_count
    for row_idx in range(row_count + 1):
        y = table_top - header_row_h - row_h * row_idx
        pdf.line(content_left, y, content_right, y)

    description = "Carga de combustible"
    if station and station.name:
        description = f"{description} - {station.name}"

    val_cell = (
        _format_liters(fuel_load.quantity_liters)
        if display_in_liters
        else _format_currency(operation_amount)
    )
    row0_bottom = table_top - header_row_h - row_h
    pdf.setFont("Helvetica", 9)
    pdf.drawString(content_left + 3 * mm, row0_bottom + 2 * mm, val_cell)
    pdf.drawString(
        content_left + val_col_w + 3 * mm, row0_bottom + 2 * mm, fuel_type_name
    )
    pdf.drawString(desc_col_x + 3 * mm, row0_bottom + 2 * mm, description)

    observations_top = table_bottom
    observations_bottom = observations_top - observations_h
    pdf.setLineWidth(1)
    pdf.rect(
        content_left,
        observations_bottom,
        content_width,
        observations_h,
        stroke=1,
        fill=0,
    )

    pdf.setFont("Helvetica", 8)
    pdf.drawString(content_left + 4 * mm, observations_top - 7 * mm, "Observaciones:")

    comments = fuel_load.comments or "-"
    pdf.setFont("Helvetica", 9)
    comment_lines = wrap(comments, width=95)
    text_y = observations_top - 12 * mm
    for line in comment_lines[:5]:
        pdf.drawString(content_left + 4 * mm, text_y, line)
        text_y -= 5 * mm

    pdf.setFont("Helvetica", 8)
    pdf.setDash(1, 2)
    sign_line_w = 45 * mm
    sign_x = content_right - sign_line_w - 6 * mm
    sign_y = observations_bottom + 12 * mm
    pdf.line(sign_x, sign_y + 10 * mm, sign_x + sign_line_w, sign_y + 10 * mm)
    pdf.drawRightString(sign_x + sign_line_w, sign_y + 8 * mm, "Firma")
    pdf.line(sign_x, sign_y, sign_x + sign_line_w, sign_y)
    pdf.drawRightString(sign_x + sign_line_w, sign_y - 2 * mm, "Aclaracion")
    pdf.setDash()

    pdf.setFillColor(colors.HexColor("#1B2F5B"))
    pdf.rect(
        content_left,
        content_bottom,
        content_width,
        bottom_bar_h,
        stroke=0,
        fill=1,
    )

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()


def build_fuel_load_remito_empresa_pdf(fuel_load, company, organism):
    """
    Genera un remito PDF para empresas/organismos.
    En lugar de nombre y DNI del usuario, muestra la empresa y el organismo.
    El CUIT y la condición ante IVA se obtienen de la empresa (company).
    """
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    operation_amount = (
        fuel_load.final_amount
        if fuel_load.final_amount is not None
        else fuel_load.initial_amount
    )
    station = fuel_load.station
    account = fuel_load.account
    display_in_liters = (account.display_type == "litros") if account else False
    fuel_type_name = fuel_load.fuel_type.name if fuel_load.fuel_type else "-"

    organism_name = organism.name if organism else "-"
    company_name = company.name if company else "-"
    organism_cuit = (company.cuit or "-") if company else "-"
    is_resp_inscripto = (
        company.tax_condition == "responsable_inscripto"
        if company and company.tax_condition
        else False
    )
    is_exento = (
        company.tax_condition == "exento"
        if company and company.tax_condition
        else False
    )

    margin = 12 * mm
    content_left = margin
    content_right = width - margin
    content_top = height - margin
    content_bottom = margin
    content_width = content_right - content_left
    content_height = content_top - content_bottom

    header_h = 45 * mm
    section1_h = 18 * mm
    section2_h = 8 * mm
    section3_h = 8 * mm
    observations_h = 45 * mm
    bottom_bar_h = 8 * mm
    table_h = content_height - (
        header_h + section1_h + section2_h + section3_h + observations_h + bottom_bar_h
    )

    if table_h < 60 * mm:
        table_h = 60 * mm
        observations_h = content_height - (
            header_h + section1_h + section2_h + section3_h + bottom_bar_h + table_h
        )

    # ---------- Marco exterior ----------
    pdf.setStrokeColor(colors.black)
    pdf.setLineWidth(1)
    pdf.rect(
        content_left, content_bottom, content_width, content_height, stroke=1, fill=0
    )

    # ---------- Header ----------
    header_top = content_top
    header_bottom = header_top - header_h
    pdf.rect(content_left, header_bottom, content_width, header_h, stroke=1, fill=0)

    left_w = content_width * 0.62
    left_x = content_left
    right_x = content_left + left_w
    right_w = content_width - left_w
    pdf.line(right_x, header_bottom, right_x, header_top)

    pdf.setFillColor(colors.HexColor("#1B2F5B"))
    pdf.setFont("Helvetica-Bold", 32)
    pdf.drawString(left_x + 6 * mm, header_top - 18 * mm, "WICO")
    pdf.setFont("Helvetica-Bold", 11)
    pdf.drawString(left_x + 7 * mm, header_top - 27 * mm, "COMBUSTIBLES")

    pdf.setFillColor(colors.black)
    pdf.setFont("Helvetica", 7.5)
    pdf.drawString(left_x + 7 * mm, header_top - 33 * mm, "COMBUSTIBLES ITALO")
    pdf.drawString(left_x + 7 * mm, header_top - 37 * mm, "ARGENTINO S.A.")
    pdf.drawString(
        left_x + 7 * mm, header_top - 41 * mm, "I.V.A. RESPONSABLE INSCRIPTO"
    )

    r_box_size = 12 * mm
    r_box_x = left_x + left_w - 28 * mm
    r_box_y = header_top - 18 * mm
    pdf.setLineWidth(1)
    pdf.rect(r_box_x, r_box_y, r_box_size, r_box_size, stroke=1, fill=0)
    pdf.setFont("Helvetica-Bold", 16)
    pdf.drawCentredString(r_box_x + r_box_size / 2, r_box_y + 3.5 * mm, "R")

    pdf.setFont("Helvetica", 6.2)
    pdf.drawCentredString(r_box_x + r_box_size / 2, r_box_y - 2 * mm, "CODIGO")
    pdf.drawCentredString(r_box_x + r_box_size / 2, r_box_y - 5.5 * mm, "Documento NO")
    pdf.drawCentredString(r_box_x + r_box_size / 2, r_box_y - 8.5 * mm, "valido como")
    pdf.drawCentredString(r_box_x + r_box_size / 2, r_box_y - 11.5 * mm, "FACTURA")

    pdf.setFont("Helvetica-Bold", 12)
    pdf.drawString(right_x + 6 * mm, header_top - 12 * mm, "REMITO")
    pdf.setFont("Helvetica", 9)
    pdf.drawRightString(
        right_x + right_w - 6 * mm, header_top - 12 * mm, f"N {fuel_load.id}"
    )

    date_box_x = right_x + 6 * mm
    date_box_y = header_top - 26 * mm
    date_box_w = right_w - 12 * mm
    date_box_h = 8 * mm
    pdf.roundRect(date_box_x, date_box_y, date_box_w, date_box_h, 2, stroke=1, fill=0)
    pdf.setFont("Helvetica", 8)
    pdf.drawString(date_box_x + 2 * mm, date_box_y + 2 * mm, "FECHA")
    pdf.drawRightString(
        date_box_x + date_box_w - 2 * mm,
        date_box_y + 2 * mm,
        _format_date(fuel_load.timestamp_finished),
    )

    pdf.setFont("Helvetica", 8)
    pdf.drawString(right_x + 6 * mm, header_top - 34 * mm, "CUIT:")
    pdf.drawString(right_x + 25 * mm, header_top - 34 * mm, "30-71611995-1")
    pdf.drawString(right_x + 6 * mm, header_top - 39 * mm, "INGR. BRUTOS:")
    pdf.drawString(right_x + 35 * mm, header_top - 39 * mm, "30-71611995-1")
    pdf.drawString(right_x + 6 * mm, header_top - 44 * mm, "INICIO ACT.:")
    pdf.drawString(right_x + 35 * mm, header_top - 44 * mm, "25/07/2018")

    # ---------- Section 1: Empresa / Organismo / CUIT ----------
    section1_top = header_bottom
    section1_bottom = section1_top - section1_h
    pdf.rect(content_left, section1_bottom, content_width, section1_h, stroke=1, fill=0)

    label_x = content_left + 4 * mm
    row1_y = section1_top - 6 * mm
    pdf.setFont("Helvetica", 9)
    pdf.drawString(label_x, row1_y, "Empresa:")
    pdf.line(
        label_x + 18 * mm, row1_y - 1 * mm, content_right - 4 * mm, row1_y - 1 * mm
    )
    pdf.drawString(label_x + 20 * mm, row1_y, company_name)

    row2_y = section1_top - 13 * mm
    pdf.drawString(label_x, row2_y, "CUIT:")
    pdf.line(label_x + 12 * mm, row2_y - 1 * mm, label_x + 65 * mm, row2_y - 1 * mm)
    pdf.drawString(label_x + 14 * mm, row2_y, organism_cuit)

    org_label_x = label_x + 72 * mm
    pdf.drawString(org_label_x, row2_y, "Organismo:")
    pdf.line(
        org_label_x + 24 * mm, row2_y - 1 * mm, content_right - 4 * mm, row2_y - 1 * mm
    )
    pdf.drawString(org_label_x + 26 * mm, row2_y, organism_name)

    # ---------- Section 2: Patente ----------
    section2_top = section1_bottom
    section2_bottom = section2_top - section2_h
    pdf.rect(content_left, section2_bottom, content_width, section2_h, stroke=1, fill=0)

    plate_y = section2_top - 5.5 * mm
    pdf.drawString(label_x, plate_y, "Patente de Vehiculo:")
    pdf.line(
        label_x + 36 * mm, plate_y - 1 * mm, content_right - 4 * mm, plate_y - 1 * mm
    )
    pdf.drawString(
        label_x + 38 * mm,
        plate_y,
        fuel_load.plate.plate_number if fuel_load.plate else "-",
    )

    # ---------- Section 3: IVA (condición del organismo) ----------
    section3_top = section2_bottom
    section3_bottom = section3_top - section3_h
    pdf.rect(content_left, section3_bottom, content_width, section3_h, stroke=1, fill=0)

    iva_y = section3_top - 5.5 * mm
    pdf.drawString(label_x, iva_y, "I.V.A.")

    def draw_checkbox(x, y, label, checked=False):
        box_size = 3.5 * mm
        pdf.rect(x, y - 2 * mm, box_size, box_size, stroke=1, fill=0)
        if checked:
            pdf.setFont("Helvetica-Bold", 8)
            pdf.drawString(x + 0.7 * mm, y - 1 * mm, "X")
            pdf.setFont("Helvetica", 8)
        pdf.drawString(x + 5 * mm, y - 0.5 * mm, label)

    checkbox_y = iva_y
    checkbox_x = label_x + 18 * mm
    pdf.setFont("Helvetica", 8)
    draw_checkbox(checkbox_x, checkbox_y, "Resp. Inscripto", checked=is_resp_inscripto)
    draw_checkbox(checkbox_x + 35 * mm, checkbox_y, "Monotributo", checked=False)
    draw_checkbox(checkbox_x + 65 * mm, checkbox_y, "Cons. Final", checked=False)
    draw_checkbox(checkbox_x + 92 * mm, checkbox_y, "Exento", checked=is_exento)

    # ---------- Tabla de montos ----------
    table_top = section3_bottom
    table_bottom = table_top - table_h
    pdf.rect(content_left, table_bottom, content_width, table_h, stroke=1, fill=0)

    header_row_h = 7 * mm
    pdf.setFillColor(colors.HexColor("#1B2F5B"))
    pdf.rect(
        content_left,
        table_top - header_row_h,
        content_width,
        header_row_h,
        stroke=0,
        fill=1,
    )
    pdf.setFillColor(colors.white)
    pdf.setFont("Helvetica-Bold", 9)

    val_col_w = 25 * mm
    fuel_col_w = 30 * mm
    desc_col_x = content_left + val_col_w + fuel_col_w
    desc_col_w = content_width - val_col_w - fuel_col_w
    val_col_header = "CANTIDAD" if display_in_liters else "MONTO"
    pdf.drawCentredString(
        content_left + val_col_w / 2, table_top - 5 * mm, val_col_header
    )
    pdf.drawCentredString(
        content_left + val_col_w + fuel_col_w / 2, table_top - 5 * mm, "COMBUSTIBLE"
    )
    pdf.drawCentredString(
        desc_col_x + desc_col_w / 2, table_top - 5 * mm, "DESCRIPCION"
    )

    pdf.setFillColor(colors.black)
    pdf.setLineWidth(0.5)
    pdf.line(
        content_left + val_col_w, table_bottom, content_left + val_col_w, table_top
    )
    pdf.line(desc_col_x, table_bottom, desc_col_x, table_top)

    row_count = 8
    row_h = (table_h - header_row_h) / row_count
    for row_idx in range(row_count + 1):
        y = table_top - header_row_h - row_h * row_idx
        pdf.line(content_left, y, content_right, y)

    description = "Carga de combustible"
    if station and station.name:
        description = f"{description} - {station.name}"

    val_cell = (
        _format_liters(fuel_load.quantity_liters)
        if display_in_liters
        else _format_currency(operation_amount)
    )
    row0_bottom = table_top - header_row_h - row_h
    pdf.setFont("Helvetica", 9)
    pdf.drawString(content_left + 3 * mm, row0_bottom + 2 * mm, val_cell)
    pdf.drawString(
        content_left + val_col_w + 3 * mm, row0_bottom + 2 * mm, fuel_type_name
    )
    pdf.drawString(desc_col_x + 3 * mm, row0_bottom + 2 * mm, description)

    # ---------- Observaciones ----------
    observations_top = table_bottom
    observations_bottom = observations_top - observations_h
    pdf.setLineWidth(1)
    pdf.rect(
        content_left,
        observations_bottom,
        content_width,
        observations_h,
        stroke=1,
        fill=0,
    )

    pdf.setFont("Helvetica", 8)
    pdf.drawString(content_left + 4 * mm, observations_top - 7 * mm, "Observaciones:")

    comments = fuel_load.comments or "-"
    pdf.setFont("Helvetica", 9)
    comment_lines = wrap(comments, width=95)
    text_y = observations_top - 12 * mm
    for line in comment_lines[:5]:
        pdf.drawString(content_left + 4 * mm, text_y, line)
        text_y -= 5 * mm

    pdf.setFont("Helvetica", 8)
    pdf.setDash(1, 2)
    sign_line_w = 45 * mm
    sign_x = content_right - sign_line_w - 6 * mm
    sign_y = observations_bottom + 12 * mm
    pdf.line(sign_x, sign_y + 10 * mm, sign_x + sign_line_w, sign_y + 10 * mm)
    pdf.drawRightString(sign_x + sign_line_w, sign_y + 8 * mm, "Firma")
    pdf.line(sign_x, sign_y, sign_x + sign_line_w, sign_y)
    pdf.drawRightString(sign_x + sign_line_w, sign_y - 2 * mm, "Aclaracion")
    pdf.setDash()

    # ---------- Barra inferior ----------
    pdf.setFillColor(colors.HexColor("#1B2F5B"))
    pdf.rect(
        content_left,
        content_bottom,
        content_width,
        bottom_bar_h,
        stroke=0,
        fill=1,
    )

    pdf.showPage()
    pdf.save()
    buffer.seek(0)
    return buffer.getvalue()
