
__all__ = [
    'get_headers',
    'build_query_filter',
    'IssuedInvoiceMapper',
    'RecievedInvoiceMapper',
    'hardcode',
]

from sets import ImmutableSet

_DATE_FMT = '%d-%m-%Y'
RECTIFIED_KINDS = ImmutableSet({'R1', 'R2', 'R3', 'R4', 'R5'})


def _format_period(period):
    return str(period).zfill(2)


def build_query_filter(year=None, period=None):
    return {
        'PeriodoImpositivo': {
            'Ejercicio': year,
            'Periodo': _format_period(period),
        }
        # TODO: IDFactura, Contraparte,
        # FechaPresentacion, FacturaModificada,
        # EstadoCuadre, ClavePaginacion
    }


def get_headers(name=None, vat=None, comm_kind=None, version='0.7'):
    return {
        'IDVersionSii': version,
        'Titular': {
            'NombreRazon': name,
            'NIF': vat,
            # TODO: NIFRepresentante
        },
        'TipoComunicacion': comm_kind,
    }


class _HardcodedValue(object):

    def __init__(self, value):
        self.value = value

    def __call__(self, *args, **kwargs):
        return self.value


def hardcode(value):
    return _HardcodedValue(value)


class BaseInvoiceMapper(object):

    def _build_period(self, invoice):
        return {
            'Ejercicio': self.year(invoice),
            'Periodo': _format_period(self.period(invoice)),
        }

    def _build_invoice_id(self, invoice):
        ret = {
            'IDEmisorFactura': self._build_issuer_id(invoice),
            'NumSerieFacturaEmisor': self.serial_number(invoice),
            'FechaExpedicionFacturaEmisor':
                self.issue_date(invoice).strftime(_DATE_FMT),
        }
        if self.invoice_kind(invoice) == 'F4':
            ret['NumSerieFacturaEmisorResumenFinal'] = \
                self.final_serial_number(invoice)
        return ret

    def _build_counterpart(self, invoice):
        return {
            'NombreRazon': self.counterpart_name(invoice),
            'NIF': self.counterpart_nif(invoice),
            # 'IDOtro': {
            #     'IDType': self.counterpart_id_type(invoice),
            #     'CodigoPais': self.counterpart_country(invoice),
            #     # 'ID': self.counterpart_nif(invoice),
            # },
        }


class IssuedInvoiceMapper(BaseInvoiceMapper):

    def build_delete_request(self, invoice):
        return {
            'PeriodoImpositivo': self._build_period(invoice),
            'IDFactura': self._build_invoice_id(invoice),
        }

    def build_submit_request(self, invoice):
        request = self.build_delete_request(invoice)
        request['FacturaExpedida'] = self.build_issued_invoice(invoice)
        return request

    def _build_issuer_id(self, invoice):
        return {
            'NIF': self.nif(invoice),
        }

    def build_issued_invoice(self, invoice):
        ret = {
            'TipoFactura': self.invoice_kind(invoice),
            # TODO: FacturasAgrupadas
            # TODO: FacturasRectificadas
            # TODO: FechaOperacion
            'ClaveRegimenEspecialOTrascendencia':
                self.specialkey_or_trascendence(invoice),
            # TODO: ClaveRegimenEspecialOTrascendenciaAdicional1
            # TODO: ClaveRegimenEspecialOTrascendenciaAdicional2
            # TODO: NumRegistroAcuerdoFacturacion
            # TODO: ImporteTotal
            # TODO: BaseImponibleACoste
            'DescripcionOperacion': self.description(invoice),
            # TODO: DatosInmueble
            # TODO: ImporteTransmisionSujetoAIVA
            # TODO: EmitidaPorTerceros
            # TODO: VariosDestinatarios
            # TODO: Cupon
            'TipoDesglose': {
                'DesgloseFactura': {
                    'Sujeta': {
                        # 'Exenta': {
                        #     'CausaExcencion': E1-E6
                        #     'BaseImponible': '0.00',
                        # },
                        'NoExenta': {
                            'TipoNoExenta': self.not_exempt_kind(invoice),
                            'DesgloseIVA': {
                                'DetalleIVA':
                                    map(self.build_taxes, self.taxes(invoice)),
                            }
                        },
                    },
                    # 'NoSujeta': {
                    #     'ImportePorArticulos7_14_Otros': 0,
                    #     'ImporteTAIReglasLocalizacion': 0,
                    # },
                },
                # 'DesgloseTipoOperacion': {
                #     'PrestacionDeServicios':
                #         {'Sujeta': {'Exenta': {}, 'NoExenta': {}}, 'NoSujeta': {}},
                #     'Entrega':
                #         {'Sujeta': {'Exenta': {}, 'NoExenta': {}}, 'NoSujeta': {}},
                # },
            },
        }
        self._update_total_amount(ret, invoice)
        self._update_counterpart(ret, invoice)
        self._update_rectified_invoice(ret, invoice)
        return ret

    def _update_total_amount(self, ret, invoice):
        if (
            ret['TipoFactura'] == 'R5' and
            len(
                ret['TipoDesglose']['DesgloseFactura']['Sujeta']['NoExenta']
                ['DesgloseIVA']['DetalleIVA']
            ) == 1 and
            (
                ret['TipoDesglose']['DesgloseFactura']['Sujeta']['NoExenta']
                ['DesgloseIVA']['DetalleIVA'][0]['BaseImponible'] == 0
            )
        ):
            ret['ImporteTotal'] = self.total_amount(invoice)

    def _update_counterpart(self, ret, invoice):
        if ret['TipoFactura'] not in {'F2', 'F4', 'R5'}:
            ret['Contraparte'] = self._build_counterpart(invoice)

    def _update_rectified_invoice(self, ret, invoice):
        if ret['TipoFactura'] in RECTIFIED_KINDS:
            ret['TipoRectificativa'] = self.rectified_invoice_kind(invoice)
            if ret['TipoRectificativa'] == 'S':
                ret['ImporteRectificacion'] = {
                    'BaseRectificada': self.rectified_base(invoice),
                    'CuotaRectificada': self.rectified_amount(invoice),
                    # TODO: CuotaRecargoRectificado
                }

    def build_taxes(self, tax):
        return {
            'TipoImpositivo': int(100 * self.tax_rate(tax)),
            'BaseImponible': self.tax_base(tax),
            'CuotaRepercutida': self.tax_amount(tax),
            # TODO: TipoRecargoEquivalencia, CuotaRecargoEquivalencia
        }


class RecievedInvoiceMapper(BaseInvoiceMapper):

    def build_delete_request(self, invoice):
        return {
            'PeriodoImpositivo': self._build_period(invoice),
            'IDFactura': self.build_named_invoice_id(invoice),
        }

    def build_submit_request(self, invoice):
        return {
            'PeriodoImpositivo': self._build_period(invoice),
            'IDFactura': self._build_invoice_id(invoice),
            'FacturaRecibida': self.build_invoice(invoice),
        }

    def _build_issuer_id(self, invoice):
        return {
            'NIF': self.counterpart_nif(invoice),
            # TODO: IDOtro: {CodigoPais, IDType, ID}
        }

    def build_named_invoice_id(self, invoice):
        return {
            'IDEmisorFactura': {
                'NombreRazon': self.counterpart_name(invoice),
                'NIF': self.counterpart_nif(invoice),
            },
            'NumSerieFacturaEmisor': self.serial_number(invoice),
            'FechaExpedicionFacturaEmisor':
                self.issue_date(invoice).strftime(_DATE_FMT),
        }

    def build_invoice(self, invoice):
        ret = {
            'TipoFactura': self.invoice_kind(invoice),
            # TODO: FacturasAgrupadas: {IDFacturaAgrupada: [{Num, Fecha}]}
            # TODO: FechaOperacion
            'ClaveRegimenEspecialOTrascendencia':
                self.specialkey_or_trascendence(invoice),
            # TODO: ClaveRegimenEspecialOTrascendenciaAdicional1
            # TODO: ClaveRegimenEspecialOTrascendenciaAdicional2
            # TODO: NumRegistroAcuerdoFacturacion
            # TODO: ImporteTotal
            # TODO: BaseImponibleACoste
            'DescripcionOperacion': self.description(invoice),
            'DesgloseFactura': {
                # 'InversionSujetoPasivo': {
                #     'DetalleIVA':
                #         map(self.build_taxes, self.taxes(invoice)),
                # },
                'DesgloseIVA': {
                    'DetalleIVA':
                        map(self.build_taxes, self.taxes(invoice)),
                }
            },
            'Contraparte': self._build_counterpart(invoice),
            'FechaRegContable': self.move_date(invoice).strftime(_DATE_FMT),
            'CuotaDeducible': self.deductible_amount(invoice),
        }
        self._update_rectified_invoice(ret, invoice)
        return ret

    def _update_rectified_invoice(self, ret, invoice):
        if ret['TipoFactura'] in RECTIFIED_KINDS:
            ret['TipoRectificativa'] = self.rectified_invoice_kind(invoice)
            # TODO: FacturasRectificadas:{IDFacturaRectificada:[{Num, Fecha}]}
            # TODO: ImporteRectificacion: {
            #   BaseRectificada, CuotaRectificada, CuotaRecargoRectificado }

    def build_taxes(self, tax):
        return {
            'TipoImpositivo': int(100 * self.tax_rate(tax)),
            'BaseImponible': self.tax_base(tax),
            'CuotaSoportada': self.tax_amount(tax),
            # TODO: TipoRecargoEquivalencia, CuotaRecargoEquivalencia
            # TODO: PorcentCompensacionREAGYP, ImporteCompensacionREAGYP
        }
