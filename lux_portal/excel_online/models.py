#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from datetime import datetime
import json
from lux_portal.extensions import db


class ExcelSheet(db.Model):
    """Una hoja (pestaña) del Excel Online. Headers y filas se guardan como
    JSON para permitir columnas dinamicas, igual que una hoja de calculo real."""
    __tablename__ = 'excel_online_sheets'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    order = db.Column(db.Integer, default=0)
    fecha_creacion = db.Column(db.DateTime, default=datetime.utcnow)
    fecha_modificacion = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    headers_json = db.Column(db.Text, default='[]')
    rows_json = db.Column(db.Text, default='[]')

    @property
    def headers(self):
        return json.loads(self.headers_json) if self.headers_json else []

    @headers.setter
    def headers(self, value):
        self.headers_json = json.dumps(value, ensure_ascii=False)

    @property
    def rows(self):
        return json.loads(self.rows_json) if self.rows_json else []

    @rows.setter
    def rows(self, value):
        self.rows_json = json.dumps(value, ensure_ascii=False)

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'order': self.order,
            'headers': self.headers,
            'rows': self.rows,
        }
