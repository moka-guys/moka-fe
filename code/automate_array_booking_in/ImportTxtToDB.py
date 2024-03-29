""" 

This script imports patients & array tests from a txt file generated by GeneWorks into Moka
It will return success and fail statements to the txt file, as well as to the user in Moka FE
It is linked to the 0202 AutoBookingInArrays form

## Debugging ##

Use --d to get more verbose error messages printed to the terminal 

All SQL statements are commented with DEBUG if these need to be added to the error messages
If a row has failed at the Patients stage, search for DEBUG PATIENT
If a row has failed at the Test stage, search for DEBUG TEST

"""

import os 
import pandas as pd
import datetime
from ConfigParser import ConfigParser 
import pyodbc 
import getpass # to get username 
import socket # to get computer name 
import ImportTxtToDBConfig as config 
import sys
import argparse 
import numpy as np



# Read config file(must be called config.ini and stored in the same directory as script)
config_parser = ConfigParser()
print_config = config_parser.read(os.path.join(os.path.dirname(os.path.realpath(__file__)), "config.ini"))

class MokaConnector(object):
    """
    pyodbc connection to Moka database for use by other functions
    
    """
    def __init__(self):
        self.cnxn = pyodbc.connect('DRIVER={{SQL Server}}; SERVER={server}; DATABASE={database};'.format(
            server=config_parser.get("MOKA", "SERVER"),
            database=config_parser.get("MOKA", "DATABASE")
            ),
            autocommit=True
        )
        self.cursor = self.cnxn.cursor()

    def __del__(self):
        """
        Close connection when object destroyed
        """
        self.cnxn.close()

    def execute(self, sql):
        """
        Execute SQL, without catching return values (INSERT, UPDATE etc.)
        """
        self.cursor.execute(sql)

    def fetchall(self, sql):
        """
        Execute SQL catching all return records (SELECT etc.)
        """
        return self.cursor.execute(sql).fetchall()

    def fetchone(self, sql):
        """
        Execute SQL catching one returned record (SELECT etc.)
        """
        return self.cursor.execute(sql).fetchone()


'''=================================================== SCRIPT FUNCTIONS=================================================== ''' 

# For debugging flag ===========================================
def arg_parse():	
	   """
	   Parses arguments supplied by the command line.
	       :return: (Namespace object) parsed command line attributes
	
	   Creates argument parser, defines command line arguments, then parses supplied command line arguments using the
	   created argument parser.
	   """
	   parser = argparse.ArgumentParser()
	   parser.add_argument('-d', '--debug', action='store_true', help="Run this mode for increased error printing")
	   return parser.parse_args()
	   
# Change apostrophes function ==================================================

def make_txt_sql_friendly(df_row):
    '''
    Single apostrophes in SQL are special characters, this creates issues with some patient's names
    This function inserts a second apostrophe to any single ones in patients names, escaping the single apostrophe in SQL  
    INPUT: The label (df_row) of the current row of the df that is being looped through by the script 
    RETURN: None
    '''
    apostrophe = "'"
    sql_apostrophe = "''"
    if apostrophe in df.loc[df_row,"LastName"]:
        # Add another apostrophe to all single ones
        df.loc[df_row,"LastName"]=  df.loc[df_row,"LastName"].replace(apostrophe, sql_apostrophe)
    if apostrophe in df.loc[df_row,"FirstName"]:
        df.loc[df_row,"FirstName"]=  df.loc[df_row,"FirstName"].replace(apostrophe, sql_apostrophe)

# Patient booking function ==========================================
def import_check_patients_table_moka(df_row):
    '''
    This function takes the label of the current row of the df being looped through (df_row)
    df.loc then finds the data in that row, in the column header named in the script eg. df.loc[df_row, "SpecimenTrustID"] 
    It inserts them into Moka if required and adds to the patient log
    It returns the df with the row completed, as well as an error handling message
    The patient_error boolean ensures errors are captured for returning to user,
    stopping other parts of the script running and for debugging.

    INPUT: The label (df_row) of the current row of the df that is being looped through by the script 
    RETURN: patient_error for error handling

    '''
    # Define patient_error boolean 
    patient_error = False 
    # See if the function can run 
    try:
        # Check if patient is in the patients table
        check_patient_specimentrustid_sql = ("SELECT [Patients].[InternalPatientID]" 
                "FROM ([dbo].[gwv-patientlinked] INNER JOIN [Patients] ON"
                "[dbo].[gwv-patientlinked].[PatientTrustID] = [Patients].[PatientID] )"
                "INNER JOIN [dbo].[gwv-specimenlinked] ON ([dbo].[gwv-patientlinked].[PatientID] = [dbo].[gwv-specimenlinked].[PatientID])"
                "WHERE [dbo].[gwv-specimenlinked].[SpecimenTrustID]='{SpecimenTrust_ID}'"
        ).format(
            SpecimenTrust_ID = df.loc[df_row, "SpecimenTrustID"] 
        )
        check_patient_specimentrustid_results = mc.fetchall(check_patient_specimentrustid_sql) 
        #error_list.append(check_patient_specimentrustid_results) #DEBUG PATIENT
        # Check if SELECT has returned any rows 
        # If this returns >1 there's two patients with this spec number in Moka, NOT GOOD 
        if len(check_patient_specimentrustid_results) > 1: 
            # For debugging          
            error = ("ERROR: {SpecimenTrust_ID} details in Moka Patients table twice!"
                    ).format(
                    SpecimenTrust_ID = df.loc[df_row,"SpecimenTrustID"] ) 
            error_list.append(error)
            df.loc[df_row,'Patient_Moka_status'] = 'Failed'
            patient_error = True
        # Patient already in Patients table      
        elif len(check_patient_specimentrustid_results) == 1:
            # There's a patient in the Patients table in Moka linked to this SpecimenTrustID
            # Now check if names match GW and Moka
            check_patient_sql = ("SELECT [Patients].[InternalPatientID]" 
                "FROM ([dbo].[gwv-patientlinked] INNER JOIN [Patients] ON"
                "[dbo].[gwv-patientlinked].[PatientTrustID] = [Patients].[PatientID] )"
                "INNER JOIN [dbo].[gwv-specimenlinked] ON ([dbo].[gwv-patientlinked].[PatientID] = [dbo].[gwv-specimenlinked].[PatientID])"
                "WHERE [dbo].[gwv-specimenlinked].[SpecimenTrustID]='{SpecimenTrust_ID}' "
                " AND [BookinLastName]= '{Last_Name}' AND [BookinFirstName]= '{First_Name}' "
            ).format(
                SpecimenTrust_ID = df.loc[df_row, "SpecimenTrustID"],
                Last_Name = df.loc[df_row,"LastName"],
                First_Name = df.loc[df_row,"FirstName"]
            )
            check_patient_results = mc.fetchall(check_patient_sql) 
            #error_list.append(check_patient_results) #DEBUG PATIENT
            # Check if SELECT has returned any rows 
            # If this returns one, there is one patient in GW who matches the entry in Moka
            if len(check_patient_results) == 1:
                # Add status to df for logging
                df.loc[df_row,'Patient_Moka_status'] = "Success"
            else:
                # Patient with a matching SpecimenTrustID is in Moka, but the first & last name in Moka are not the same as in GW
                # error flag, do not proceed
                error = ("ERROR: Can't find {SpecimenTrust_ID} in GW. Names in Moka & GW might not match"
                ).format(
                SpecimenTrust_ID = df.loc[df_row,"SpecimenTrustID"] ) 
                error_list.append(error)
                df.loc[df_row,'Patient_Moka_status'] = "Failed: Moka & GW patient names do not match"
                patient_error = True    
        # There's no patient in Moka with a link to that SpecimenTrustID
        # To add them into the patients table! Get info from GW to insert into Moka 
        else:   
            get_patient_ID_sql = ("SELECT [dbo].[gwv-patientlinked].[PatientTrustID], [dbo].[gwv-patientlinked].[DoB]" 
                "FROM [dbo].[gwv-specimenlinked] INNER JOIN [dbo].[gwv-patientlinked] "
                    "ON [dbo].[gwv-patientlinked].[PatientID] = [dbo].[gwv-specimenlinked].[PatientID]"
                        "WHERE [dbo].[gwv-specimenlinked].[SpecimenTrustID]='{SpecimenTrust_ID}' "
                            "AND [LastName]= '{Last_Name}' AND [FirstName]= '{First_Name}' "
            ).format(
                SpecimenTrust_ID = df.loc[df_row,"SpecimenTrustID"],
                Last_Name = df.loc[df_row,"LastName"],
                First_Name = df.loc[df_row,"FirstName"]
            )
            #error_list.append(get_patient_ID_sql) #DEBUG PATIENT
            # Run SQL, returns a list of tuples
            get_patient_ID_result = mc.fetchall(get_patient_ID_sql) 
            # get_patient_ID_result returns the result of a query in a list of tuples, 
            # where the tuple contains (PatientTrustID, DOB)
            PatientTrustID = get_patient_ID_result[0][0]
            # Make the DOB to three SF from GW six
            Patient_DOB = date_time_three_sf(get_patient_ID_result[0][1])
            # If it does not return 1, there's no patient in GW 
            if len(get_patient_ID_result) != 1: 
                error = ("ERROR: Can't find {SpecimenTrust_ID} in GW "
                ).format(
                SpecimenTrust_ID = df.loc[df_row,"SpecimenTrustID"] ) 
                error_list.append(error)
                df.loc[df_row,'Patient_Moka_status'] = 'Failed' 
                patient_error = True                 
            else: 
                # The patient is in GW & values have been returned
                # Check the name of the patient in the txt file matches the GW PatientTrustID returned from previous SQL
                check_patient_GW_ID_sql = ("SELECT [dbo].[gwv-patientlinked].[PatientTrustID]" 
                                "FROM [dbo].[gwv-patientlinked] "
                                "WHERE [PatientTrustID]='{Patient_ID}' AND [LastName]= '{Last_Name}' "
                                "AND [FirstName]= '{First_Name}' "
            ).format(
                Patient_ID = PatientTrustID,
                Last_Name = df.loc[df_row,"LastName"],
                First_Name = df.loc[df_row,"FirstName"],
            )
                check_patient_GW_ID_result = mc.fetchall(check_patient_GW_ID_sql) 
                if len(check_patient_GW_ID_result) != 1: 
                    error = ("ERROR: {SpecimenTrust_ID} in GW, does not match names in txt file "
                    ).format(
                    SpecimenTrust_ID = df.loc[df_row,"SpecimenTrustID"] ) 
                    error_list.append(error)
                    df.loc[df_row,'Patient_Moka_status'] = 'Failed' 
                    patient_error = True               
                else: 
                    # Everything matches!
                    # Insert patient into patients table 
                    patient_error = False
                    # Assign the first part of the returned value (PatientTrustID(GW)/InternalPatientID(Moka))
                    insert_patient_sql = ("INSERT INTO [Patients] ([PatientID], [s_StatusOverall], [BookinLastName],"
                                        "[BookinFirstName], [BookinSex], [BookinDOB], [MokaCreated], [MokaCreatedBy], [MokaCreatedPC])" 
                                        "VALUES ('{Patient_ID}', '{Patient_Status}', '{Last_Name}', '{First_Name}',"
                                        "'{Sex}', '{Date_of_birth}', '{Created_date}' , '{Staff_username}', '{Staff_PC}')" 
                    ).format(
                        # Use the return to fill the insert query 
                        Patient_ID = PatientTrustID, 
                        Patient_Status = config.status_inprogress,
                        Last_Name = df.loc[df_row,"LastName"],
                        First_Name = df.loc[df_row,"FirstName"],
                        Sex = df.loc[df_row,"Gender"],
                        Date_of_birth = Patient_DOB,
                        Created_date= date_time,
                        Staff_username = username,
                        Staff_PC = computer_name
                    )
                    #error_list.append(insert_patient_sql) # DEBUG PATIENT
                    mc.execute(insert_patient_sql) 
                    # Return the primary key (InternalPatientID) for new insert
                    patients_table_primary_key = mc.fetchone("SELECT @@IDENTITY")[0]
                    # Check all info from the txt and returned primary key is correct
                    check_patient_insert_sql = ("SELECT [Patients].[InternalPatientID] "
                                    "FROM [Patients]" 
                                    "WHERE [InternalPatientID] =  '{Internal_PT_ID}' AND [PatientID]='{Patient_ID}' AND [BookinLastName]= '{Last_Name}' "
                                    "AND [BookinFirstName]= '{First_Name}' AND [BookinSex]= '{Sex}' "
                                    "AND [BookinDOB] = '{Date_of_birth}' AND [MokaCreated]='{Created_date}'"
                    ).format(
                        Internal_PT_ID = patients_table_primary_key,
                        Patient_ID = PatientTrustID,
                        Last_Name = df.loc[df_row,"LastName"],
                        First_Name = df.loc[df_row,"FirstName"],
                        Sex = df.loc[df_row,"Gender"],
                        Date_of_birth = Patient_DOB,
                        Created_date= date_time,
                    )
                    #error_list.append(check_patient_insert_result) # DEBUG PATIENT
                    check_patient_insert_result = mc.fetchall(check_patient_insert_sql) 
                    # If this returns 1, the patient has been added successfully 
                    if len(check_patient_insert_result) == 1: 
                        df.loc[df_row,'Patient_Moka_status'] = "Success"
                        # Add this successful addition to the patient log 
                        insert_log_patient_sql = ("INSERT INTO PatientLog([InternalPatientID], [LogEntry], [Date], [Login], [PCName]) "
                                "VALUES ('{Internal_PT_ID}', 'New Patient added to Patients table {Internal_PT_ID} "
                                "using the Automating booking in arrays script version {Script_version}',"
                                "'{Created_date}', '{Staff_username}' , '{Staff_PC}')" 
                        ).format(
                            Internal_PT_ID = patients_table_primary_key, 
                            Script_version = config.scriptversion, 
                            Created_date= date_time,
                            Staff_username = username,
                            Staff_PC = computer_name
                        )  
                        mc.execute(insert_log_patient_sql) 
                    else: 
                        error = ("ERROR: Inserting {SpecimenTrust_ID} into Patient's table failed "
                    ).format(
                        SpecimenTrust_ID = df.loc[df_row,"SpecimenTrustID"] ) 
                        error_list.append(error)
                        df.loc[df_row,'Patient_Moka_status'] = 'Failed'
                        patient_error = True                                      
    # If the function fails in an unexpected way 
    except Exception as e:
        patient_error = True  
        df.loc[df_row,'Patient_Moka_status'] = 'Error'
        error = ("ERROR: Patient booking raised an unexpected error for {SpecimenTrust_ID}"
        ).format(
            SpecimenTrust_ID = df.loc[df_row, "SpecimenTrustID"]
        )  
        # For debugging
        SQL_error = "This is the SQL error:"
        error_list.append(error)
        error_list.append(SQL_error)
        error_list.append(e)
    return(patient_error)

# Test booking function ========================================================================

def import_check_array_table_moka(df_row):
    '''
    This function checks if there is a test in the ArrayTest table for the Patient.
    If there isn't a test or if there is at test and the status is Complete (4) or Not Possible (5) another test is added.
    If there is a test and it has any other status (which means it's ongoing), nothing is done.
    The test_error flag ensures errors are captured for returning to user,
    stopping other parts of the script running and for debugging.

    INPUT: The index of the current row of the df that is being looped through by the script 
    RETURN: test_error for error handling

    '''
    #  Define test_error boolean
    test_error = False 
    # See if the function can run
    try:
        # Check a test for this SpecimenTrustID is already in the ArrayTest table 
        # but does not have the status complete or not possible 
        check_ArrayTest_sql = ("SELECT [ArrayTest].[ArrayTestID]" 
                                "FROM ( [Patients] INNER JOIN [ArrayTest] ON [Patients].[InternalPatientID] = [ArrayTest].[InternalPatientID])"
                                "INNER JOIN ([dbo].[gwv-specimenlinked] INNER JOIN [dbo].[gwv-patientlinked] ON"
                                "[dbo].[gwv-patientlinked].[PatientID] = [dbo].[gwv-specimenlinked].[PatientID])"
                                "ON  [dbo].[gwv-patientlinked].[PatientTrustID] = [Patients].[PatientID]"
                                "WHERE ([dbo].[gwv-specimenlinked].[SpecimenTrustID]='{SpecimenTrust_ID}'"
                                "AND [ArrayTest].[StatusID] NOT IN (4,5))"  
                        ).format(
                            SpecimenTrust_ID = df.loc[df_row,"SpecimenTrustID"] 
                        )
        #error_list.append(check_ArrayTest_sql) # DEBUG TEST
        check_ArrayTest_result = mc.fetchall(check_ArrayTest_sql) 
        # If this returns 1, there is an ongoing test already
        if len(check_ArrayTest_result) == 1:   
                df.loc[df_row,'Booking_in_sample_status'] = "Test already booked in with a status that is 'not possible' or 'completed'"
        # Patient is either in the DNA table with a completed/not possible status or not in there at all, to be inserted!
        else: 
            # Get data to form INSERT statement below 
            get_Array_data_sql = ("SELECT [Patients].[InternalPatientID], [dbo].[gwv-specimenlinked].[SpecimenID],  "
                " [dbo].[gwv-specimenlinked].[CreatedDate]" 
                " FROM ([dbo].[gwv-patientlinked] INNER JOIN [Patients] ON "
                "[dbo].[gwv-patientlinked].[PatientTrustID] = [Patients].[PatientID] )"
                "INNER JOIN [dbo].[gwv-specimenlinked] ON ([dbo].[gwv-patientlinked].[PatientID] = [dbo].[gwv-specimenlinked].[PatientID])"
                "WHERE [dbo].[gwv-specimenlinked].[SpecimenTrustID]='{SpecimenTrust_ID}'"
        ).format(
                SpecimenTrust_ID = df.loc[df_row,"SpecimenTrustID"] 
            )
            #error_list.append(get_Array_data_sql) # DEBUG TEST
            # get_Array_data_sql_result returns the result of a query in a list of tuples, 
            # where the tuple contains (InternalPatientID, SpecimenID, CreatedDate)
            get_Array_data_sql_result = mc.fetchall(get_Array_data_sql)
            # Get Check1ID of person running script, this is needed for ArrayTest table 
            get_check1ID_sql = ("SELECT [Checker].[Check1ID]" 
                            "FROM [Checker] "
                            "WHERE [Checker].[UserName]='{Staff_username}'"
            ).format(
                Staff_username = username
            )
            #error_list.append(get_check1ID_sql) # DEBUG TEST
            date_to_squish = get_Array_data_sql_result[0][2]
            # Make datetime three SF
            adjusted_referall_date = date_time_three_sf(date_to_squish) 
            get_check1ID_result = mc.fetchall(get_check1ID_sql)
            insert_ArrayTest_sql = ("INSERT INTO [ArrayTest] ([InternalPatientID], [GWSpecID], [ReferralID], [StatusID], "
                                        "[Priority], [RequestedDate], [BookedByID]) "
                                        " VALUES ('{Patient_ID}','{GW_Spec_no}', '{Patient_referral}','{Patient_Status}', "
                                        " '{Priority_test}','{Requested_date}',  '{Booked_in_by}')" 
            ).format(
                # get_Array_data_sql_result returns the result of a query in a list of tuples, 
                # where the tuple contains (InternalPatientID, SpecimenID, CreatedDate)
                Patient_ID = get_Array_data_sql_result[0][0], 
                GW_Spec_no = get_Array_data_sql_result[0][1],
                Patient_Status = config.status_arraytobebookedin,
                Priority_test = df.loc[df_row,"Urgency"], 
                Patient_referral = config.referral_arraytobebookedin,
                Requested_date = adjusted_referall_date, 
                Staff_PC = computer_name,
                # get_check1ID_result returns the result of a query in a list of tuples, 
                # where the tuple contains a single entry (Check1ID)
                Booked_in_by = get_check1ID_result[0][0]
            )
            #error_list.append(insert_ArrayTest_sql) # DEBUG TEST
            mc.execute(insert_ArrayTest_sql)
            # Return the newly generated ArrayTestID
            arraytest_primary_key = mc.fetchone("SELECT @@IDENTITY")[0] 
            # Check arraytestID and InternalPatientID match those in the txt file 
            check_arraytest_after_insert_sql = ("SELECT [ArrayTest].[ArrayTestID]"
                                        "FROM [ArrayTest] INNER JOIN [Patients] ON [ArrayTest].[InternalPatientID] = "
                                        " [Patients].[InternalPatientID]  "
                                        "WHERE [ArrayTest].[ArrayTestID] = '{Array_test_ID}' AND [Patients].[InternalPatientID] = '{Patient_ID}'"
                                        " AND [Patients].[BookinLastName]= '{Last_Name}' AND [Patients].[BookinFirstName]= '{First_Name}' "
                                        " AND [ArrayTest].[StatusID] = '{Patient_Status}' "                   
            ).format(
                Array_test_ID = arraytest_primary_key,
                Patient_ID = get_Array_data_sql_result[0][0],
                Last_Name = df.loc[df_row,"LastName"],
                First_Name = df.loc[df_row,"FirstName"],
                Patient_Status = config.status_arraytobebookedin
            )
            #error_list.append(check_arraytest_after_insert_sql) # DEBUG TEST 
            check_arraytest_after_insert_result = mc.fetchall(check_arraytest_after_insert_sql)
            # If this returns 1, the patient has successfully been booked in 
            if len(check_arraytest_after_insert_result) != 1: 
                error = ("ERROR: Inserting {SpecimenTrust_ID} into ArrayTest table failed "
                    ).format(
                        SpecimenTrust_ID = df.loc[df_row,"SpecimenTrustID"] ) 
                error_list.append(error)
                df.loc[df_row,'Booking_in_sample_status'] = 'Failed'   
                test_error = True
            else:
                test_error = False
                df.loc[df_row,'Booking_in_sample_status'] = 'Success' 
                # Update patient log
                insert_patient_log_array_sql = ("INSERT INTO PatientLog([InternalPatientID], [LogEntry], [Date], [Login], [PCName])"
                                    "VALUES ('{Patient_ID}', 'New ArrayTest {Array_test_ID}"
                                    " using the Automating booking in arrays script version {Script_version}' ,"
                                    " '{Created_date}', '{Staff_username}' , '{Staff_PC}')" 
                ).format(
                    Patient_ID = get_Array_data_sql_result[0][0], 
                    Array_test_ID = arraytest_primary_key,
                    Script_version = config.scriptversion,
                    Created_date = date_time,
                    Staff_username = username,
                    Staff_PC = computer_name
                )  
                mc.execute(insert_patient_log_array_sql)  
                # Update Patients status in the Patients table to Array
                update_patient_status_sql = ("UPDATE [Patients] "   
                                    " SET [s_StatusOverall] = '{Patient_Status}'"
                                    " WHERE [InternalPatientID] = '{Patient_ID}' "    
                ).format(       
                    Patient_Status = config.status_array,
                    Patient_ID = get_Array_data_sql_result[0][0]
                )
                #error_list.append(sql_update_status) # DEBUG TEST 
                mc.execute(update_patient_status_sql)
                insert_patient_log_status_sql = ("INSERT INTO PatientLog([InternalPatientID], [LogEntry], [Date], [Login], [PCName]) "
                                        "VALUES ('{Patient_ID}', 'Patient status updated to Array " 
                                        "using the Automating booking in arrays script version {Script_version}',"
                                        " '{Created_date}', '{Staff_username}' , '{Staff_PC}')" 
                ).format(
                    Patient_ID = get_Array_data_sql_result[0][0], 
                    Script_version = config.scriptversion,
                    Created_date = date_time,
                    Staff_username = username,
                    Staff_PC = computer_name
                )  
                mc.execute(insert_patient_log_status_sql) 
    # If the function fails in an unexpected way 
    except Exception as e:      
        test_error = True 
        df.loc[df_row,'Booking_in_sample_status'] = 'Error' 
        SQL_error = "This is the SQL error:"
        error = ("ERROR: Test booking raised an unexpected error for {SpecimenTrust_ID}"
        ).format(
            SpecimenTrust_ID = df.loc[df_row, "SpecimenTrustID"]
        )  
        # For debugging
        error_list.append(error)
        error_list.append(SQL_error)
        error_list.append(e)
    return(test_error)
    
# Error handling ========================================================================

def error_handling():
    '''
    Checks df for error messages.
    Prints success or fail statement to user in Moka 
    Extra logging if debug flag used 

    INPUT: None
    RETURN: None

    '''
    # Count for number of samples which have errors & how many have passed 
    count_failed = 0 
    count_passed = 0
    # Script is being run in debug mode, 
    # Print the error list, which will contain more verbose explanations of any errors that have occurred 
    if args.debug == True: 
        print(error_list) 
    # Create a loop to go through the df
    for df_row in range(len(df)): 
        if df.loc[df_row,'Processed_status'] == 'FAILED' or df.loc[df_row,'Processed_status'] == 'Error':
            count_failed +=1 
            # To ensure error flagging happens if the main script is not re run (because samples are completed or failed) but there are failed samples in it 
            error_occurred = True 
        elif df.loc[df_row,'Processed_status'] == 'Completed':
            count_passed +=1 
        # if this is the last row of the df, get the count of failed rows                     
        if df_row == len(df) - 1:
            if count_failed >= 1:
                # Flags as pop up to user in Moka 
                print('An error occurred in ' +str(count_failed)+' sample/s. Please see the txt file for error messages') 
            else:
                print('Success! ' +str(count_passed)+' sample/s imported into Moka with no errors' ) 

# Save & move txt file ========================================================================

def save_move_txt(to_process_path, file):
    '''
    Save the df to the same txt file 
    If no errors occurred, it moves the file to the /Booked directory 

    INPUT: to_process_path is defined at the start of the loop as the path to the txt tile
    file is the name of the txt file currently being processed by the script
    RETURN: None  

    '''
    df.to_csv(to_process_path, sep ='\t', index = False)            
    # If no errors, move file to /Booked directory
    if error_occurred != True: 
        processed_path = os.path.join(config.processed_path+"/"+file)
        try: 
            # Try to move the completed txt file 
            os.rename((to_process_path), (os.path.join(config.processed_path+"/"+file)))
        except:
            df['Move'] = 'Could not move file to /Booked folder. Is there a file with the same name in that folder?'
            df.to_csv(to_process_path, sep ='\t', index = False) 
            # Flags as pop up to user in Moka
            print("All test successfully completed but there's another file already in the /Booked folder with this file name. Please move manually")  
    else:
        print('File not moved to /Booked folder due to a processing failure')                   


# Make date time three significant figures =========================== 
def date_time_three_sf(t):
    '''
    Make all date times fit with Mokas requirement of being three sig figs (Some from GW are six)
    '''
    # check if there will be rounding up
    if t.microsecond % 1000 >= 500:
        # manually round up  
        t = t + datetime.timedelta(milliseconds=1)  
    t = t.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]
    return(t)

# Define variables ===============

def txt_file_variables():
    '''
    Refreshes variables for txt file

    INPUT: None
    RETURN: Variables refereshed for each txt file that is run through the script
    '''
    # Get the current date time
    t = datetime.datetime.now() 
    # Call function to make t three sig figs
    date_time = date_time_three_sf(t) 
    # List to collect errors for debugging
    error_list = [] 
    error_occurred = False 
    return(date_time, error_list, error_occurred)

'''================== One off variables =========================== '''
# Instantiate moka connector
mc = MokaConnector()
# Get username   
username = getpass.getuser() 
# Get computer name 
computer_name = socket.gethostname() 
args = arg_parse()

'''================== Run script =========================== ''' 
try:
    for file in os.listdir(config.path):
        # Look for all .txt files in the folder  
        if file.endswith(".txt"):
            # Define variables here to reset when each new .txt file is loaded 
            date_time, error_list, error_occurred = txt_file_variables() 
            to_process_path = os.path.join(config.path+"/"+file)
            # Each row of this df is an single patient 
            df = pd.read_csv(to_process_path, delimiter = "\t")
            # Fill rows with no gender to unknown 
            df['Gender'] = df['Gender'].fillna('unknown') 
            # Change to match Patients table in Moka
            df['Gender'] = df['Gender'].replace(['Female','Male'],['F','M'])
            # Change to match ArrayTest table in Moka 
            df['Urgency'] = df['Urgency'].replace(['Urgent','Routine'],['True','False'])     
            if 'Processed_status' not in df.columns:
                # Add column to df & populate it with zeros 
                df['Processed_status'] = 0
            # Flag to be processed     
            df['Processed_status'] = df['Processed_status'].fillna(0)
            # Create a loop to go through the df , based on the row labels 
            for df_row in range(len(df)): 
                # Don't re run a row that's already been processed  
                if df.loc[df_row,'Processed_status'] == 0:
                    # Make apostrophes in patients names SQL friendly 
                    make_txt_sql_friendly(df_row)
                    # Attempt to book Patient into Moka 
                    # patient_error boolean will be set to True in the function if an error does occur     
                    patient_error = import_check_patients_table_moka(df_row)
                    if patient_error == True: 
                        df.loc[df_row,'Processed_status'] = 'FAILED' 
                        error_occurred = True
                    else: 
                        # Run ArrayTable function for those rows which didn't fail
                        # test_error boolean will be set to True in the function if an error does occur
                        test_error = import_check_array_table_moka(df_row) 
                        if test_error == True: 
                            df.loc[df_row,'Processed_status'] = 'FAILED'
                            error_occurred = True
                        else:
                            # Row completed, all processing done
                            df.loc[df_row,'Processed_status'] = 'Completed' 
                # Check if this is the last row of the data frame
                if df_row == len(df) - 1:
                    # Run error handling, additional prints if debug flag used 
                    error_handling() 
                    # Swap columns back before saving txt file
                    df['Gender'] = df['Gender'].replace(['F','M'],['Female','Male'])
                    df['Urgency'] = df['Urgency'].replace(['True','False'], ['Urgent','Routine']) 
                    # Run save and move 
                    save_move_txt(to_process_path, file)                                             
except: 
    # Print to user in Moka 
    print('ERROR: Script not run. Send the below error message to Bioinformatics team') 
    if args.debug == True:
        print('Script unexpectedly broken', sys.exc_info()[0]) # Print the error to the terminals 
