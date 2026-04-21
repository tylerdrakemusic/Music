from fpdf import FPDF

# Define checklist items
belongings = [
    "Guitar", "Guitar Stand", "Amp", "Amp stand", "Trombone", "Trombone stand",
    "Music Stand", "Gig Bag", "Sheet Music", "Pedal Board", "Lights"
]

# Create PDF
pdf = FPDF(orientation='L', unit='mm', format='A4')
pdf.add_page()
pdf.set_font("Arial", size=12)
pdf.set_fill_color(240, 240, 240)

# Header
pdf.set_font("Arial", "B", 17)
pdf.cell(0, 25, "Belongings Verification Checklist", ln=True, align='C')
pdf.ln(5)
pdf.set_font("Arial", size=12)

# Dimensions
checkbox_size = 5
spacing = 10
margin = 10

# Draw rows
for item in belongings:
    pdf.cell(40, spacing, item, border=1, fill=True)
    for _ in range(25):
        pdf.cell(checkbox_size, spacing, '', border=1)
        pdf.cell(5, spacing, '', ln=0)
    pdf.ln()

# Save the PDF
output_path = "Belongings_Checklist.pdf"
pdf.output(output_path)

output_path
