"""
Carbon footprint calculator for biofuels.

Calculates the CO₂ equivalent savings (kgCO2e) compared to conventional
fossil fuels for each supported biofuel type.

Supported fuel types:
  - B20  (Biodiesel 20 %)
  - E17  (Bioethanol 17 %) — placeholder, not yet implemented
"""

from decimal import Decimal

# ─── B20 Constants ────────────────────────────────────────────────────────────

# Fraction of biodiesel in the blend
B20_BIOFUEL_PCT = Decimal("0.20")  # 20 %

# Mandatory biofuel cut established by national regulations
B20_MANDATORY_CUT = Decimal("0.075")  # 7.5 %

# Energetic correlation factor (biodiesel vs. gasoil)
B20_CORRELATION_FACTOR = Decimal("1.04")

# Emission factor of displaced gasoil (kgCO2eq / litre)
B20_FE_GASOIL = Decimal("2.73")

# CH4 + N2O emissions from the combustion of the extra biodiesel (kgCO2eq / litre)
B20_CH4_N2O_FACTOR = Decimal("0.0431")


def calculate_b20_carbon_saving(quantity_liters: Decimal) -> Decimal:
    """
    Returns the net CO2e avoided (kgCO2e) for a B20 load of *quantity_liters* litres.

    Step-by-step:
      consumo_litros               = quantity_liters
      consumo_biodiesel_total      = consumo_litros × 0.20
      consumo_biodiesel_obligatorio= consumo_litros × 0.075
      consumo_extra                = consumo_biodiesel_total − consumo_biodiesel_obligatorio
                                   = consumo_litros × 0.125

      emisiones_desplazadas_gasoil = consumo_extra × 1.04 × 2.73
      emisiones_CH4_N2O            = consumo_extra × 0.0431
      emisiones_totales_evitadas   = emisiones_desplazadas_gasoil − emisiones_CH4_N2O
    """
    liters = Decimal(str(quantity_liters))
    consumo_extra = liters * (B20_BIOFUEL_PCT - B20_MANDATORY_CUT)
    emisiones_desplazadas = consumo_extra * B20_CORRELATION_FACTOR * B20_FE_GASOIL
    emisiones_ch4_n2o = consumo_extra * B20_CH4_N2O_FACTOR
    result = emisiones_desplazadas - emisiones_ch4_n2o
    return max(Decimal("0"), result).quantize(Decimal("0.0001"))


# ─── E17 Constants ────────────────────────────────────────────────────────────
# Source: IRAM / SAyDS methodology for E17 bioethanol in Argentina

# Fraction of bioethanol in the blend
E17_BIOFUEL_PCT = Decimal("0.17")  # 17 %

# Mandatory bioethanol cut established by national regulations
E17_MANDATORY_CUT = Decimal("0.12")  # 12 %

# Energetic correlation factor (bioethanol vs. nafta)
E17_CORRELATION_FACTOR = Decimal("0.66")

# Emission factor of displaced nafta (kgCO2eq / litre)
E17_FE_NAFTA = Decimal("2.35")

# CH4 + N2O emissions from the combustion of the extra bioethanol (kgCO2eq / litre)
E17_CH4_N2O_FACTOR = Decimal("0.06030")


def calculate_e17_carbon_saving(quantity_liters: Decimal) -> Decimal:
    """
    Returns the net CO2e avoided (kgCO2e) for an E17 load of *quantity_liters* litres.

    Step-by-step:
      consumo_litros                  = quantity_liters
      consumo_bioetanol_total         = consumo_litros × 0.17
      consumo_bioetanol_obligatorio   = consumo_litros × 0.12
      consumo_extra                   = consumo_bioetanol_total − consumo_bioetanol_obligatorio
                                      = consumo_litros × 0.05

      emisiones_desplazadas_nafta     = consumo_extra × 0.66 × 2.35
      emisiones_CH4_N2O               = consumo_extra × 0.06030
      emisiones_totales_evitadas      = emisiones_desplazadas_nafta − emisiones_CH4_N2O
    """
    liters = Decimal(str(quantity_liters))
    consumo_extra = liters * (E17_BIOFUEL_PCT - E17_MANDATORY_CUT)
    emisiones_desplazadas = consumo_extra * E17_CORRELATION_FACTOR * E17_FE_NAFTA
    emisiones_ch4_n2o = consumo_extra * E17_CH4_N2O_FACTOR
    result = emisiones_desplazadas - emisiones_ch4_n2o
    return max(Decimal("0"), result).quantize(Decimal("0.0001"))


def calculate_carbon_saving(fuel_type_name: str, quantity_liters: Decimal) -> Decimal:
    """
    Dispatches to the correct calculator based on *fuel_type_name*.

    Matching is case-insensitive and substring-based (e.g. "Biodiesel B20"
    or "B20 Córdoba" will both match the B20 calculator).

    Returns Decimal("0") for fuel types that are not recognised biofuels.
    """
    if not fuel_type_name or not quantity_liters or quantity_liters <= 0:
        return Decimal("0")

    name_lower = fuel_type_name.lower().strip()

    if "b20" in name_lower:
        return calculate_b20_carbon_saving(quantity_liters)

    if "e17" in name_lower:
        return calculate_e17_carbon_saving(quantity_liters)

    return Decimal("0")
