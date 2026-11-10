# Hängt % an, sofern noch kein % im Text steht und das Feld nicht leer ist
pensum_clean = pensum_raw.strip()
if pensum_clean and not pensum_clean.endswith("%"):
    pensum = f"{pensum_clean}%"
else:
    pensum = pensum_clean
