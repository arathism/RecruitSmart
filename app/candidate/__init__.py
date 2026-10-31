from flask import Blueprint
bp = Blueprint('candidate', __name__)
from app.candidate import routes
