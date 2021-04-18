'''Form model that takes user input for experiment parameters'''

from wtforms import SubmitField, BooleanField, StringField, PasswordField, validators, IntegerField, FileField
from flask_wtf import FlaskForm
from flask_wtf.file import FileRequired

# Regex that verifies user input of field vm_csv
vmRegex = '(?:^|,)(?=[^"]|(")?)"?((?(1)[^"]*|[^,"]*))"?(?=,|$)'
# Regex that verifies user input of field test_flags_csv
testRegex = '(([^\s,=]+=[^\s,=]+)(?:,\s*)?)+|ALL'

class RegForm(FlaskForm):
    vm_csv = StringField('List of VM Images (Format: image1, image2, ..., imageN)', [validators.DataRequired(), validators.Regexp(vmRegex, message='Please put your VM image list in described format.')])
    test_flags_csv = StringField('Flag Values To Test (Format: encr=SYM, trav=BFS, ...). Type ALL if want to test all permutations.', [validators.DataRequired(), validators.Regexp(testRegex, message='Please put test flag list in described format (or ALL for all test cases).')])
    num_instances = IntegerField('Max # Of Instances', [validators.required()])
    experiment_name = StringField('Name to be used as a unique identifier for these test cases.', [validators.DataRequired()])
    file_field = FileField('Payload to be tested', validators=[FileRequired()])
    submit = SubmitField('Submit')
