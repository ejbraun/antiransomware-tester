if [ $# -eq 4 ]
then
  gcloud sql instances create $1 \
    --database-version=MYSQL_5_7 \
    --cpu=2 \
    --memory=8192MB \
    --root-password=$2

  gcloud sql users create $3 \
    --instance=$1 \
    --password=PASSWORD

  gcloud sql databases create $4 \
  --instance=$1
  echo "Script execution complete!"
else
    echo "Please call script as follows: ./createSQLInstanceAndDB.sh [INSTANCE_NAME] [ROOT_PASSWORD] [USER_NAME] [DATABASE_NAME]"
fi
