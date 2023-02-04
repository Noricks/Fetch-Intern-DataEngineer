# General Information
This is the answer for the test of "Data Engineer"

# How to run
## Run with `docker-compose`
### Requirements
- docker
- docker-compose
### Tested Environment
- Ubuntu 20.04 in WSL2

### Steps
1. Clone the repository
2. Run `docker-compose up`
3. You could see the output in the terminal
4. To see the results you could run following bash scripts. You can interact with the database in the container that the python program runs.
```bash
    # You are in the host machine running the docker-compose now
    ssh root@localhost -p 4000 # password: passwd
    
    # You are in the container now
    PGPASSWORD=postgres psql -d postgres -U postgres -p 5432 -h postgres -c "SELECT * FROM user_logins"
```
5. Use `Ctrl+C` to stop the whole docker-compose as well as the python program
   - It takes several seconds to wait for the program to clean up the queue and exit
   - Unfortunately, there is a long existing problem of docker compose that it will stop recording the logs after the program exits. Additional information during clean-up stage is ignored. 

## Run in the local machine
### Requirements
- Python 3.10
- pip
- awscli-local 
- awscli 
- psycopg2 
- cryptography

### Steps
1. Clone the repository
2. Run with `python3 main.py --local` since the docker-compose version will redirect the network to the localstack container. You could see the output in the terminal
3. Use `Ctrl+C` to stop the program
   - It takes several seconds to wait for the program to clean up the queue and exit
   - In a local environment, you can see the logs for cleaning after the `Ctrl+C` is pressed.
4. To see the results you could run following bash scripts.
```bash
    PGPASSWORD=postgres psql -d postgres -U postgres -p 5432 -h localhost -c "SELECT * FROM user_logins"
```
# Design Ideas

## How will you read messages from the queue?
- I create a thread to read the message
- The thread execute the `awslocal sqs receive-message` command through bash using `subprocess` to read the message
- It uses the network name `localstack` to connect to the localstack container in the docker-compose

## What type of data structures should be used?
- I use a `Queue` to store the un-resolved information
- It is a first-in-first-out data structure, which will resolve the information in the order of the time they are inserted
- Meanwhile, `Queue` in python is thread-safe, which is suitable for the multi-threading environment

## How will you mask the PII data so that duplicate values can be identified?
- I use the AES encryption algorithm with the same key to mask the PII data
- It will generate the same encrypted data for the same PII data and different encrypted data for different PII data

## What will be your strategy for connecting and writing to Postgres?
- I use the `psycopg2` library to connect to the database
- And I could execute the SQL command through the `cursor.execute()` function

## Where and how will your application run?
Please refer to the How to run section


# Questions

## How would you deploy this application in production?
As it is presented in the `docker-compose.yml` and the customized `Dockerfile.awslocal`. I would use `docker-compose` to deploy the application along with the database in production. The reason is that it is easy to use and maintain. It is also easy to scale up the application by adding more containers.

## What other components would you want to add to make this production ready?
### Python
- Introduce more unit/integration tests
  - Sorry that I don't have enough time to find the way to show the tests through `docker-compose` and write the tests. 
- Use `argparse` to parse the arguments
  - argparse the information of the database, making it possible to insert into a different database without changing the code
- Refactor the code to make it more readable
- Introduce better and comprehensive error handling during different scenarios like the connection to the database fails
- Introduce better approaches to store the un-resolved information (*e.g.* file) in the queue when exiting the program
- Wrap the code into a class
- Wrap the global variables into class/functions and remove `global` keyword
  - Replace the global variables with `self.shutdown_flag = threading.Event()` to make it thread-safe
- Use a better crpyto library to mask the PII data

### Dockerfile/Compose
- Pass the arguments into the docker-compose and dockerfile instead of hard code them
- Fix the version of the software (*e.g.* python) in case of the incompatibility of the new version

## How can this application scale with a growing dataset.
- Increase the number of threads or processes in the python program
- Add more containers to the docker-compose to scale up the application
- Utilize Kubernetes to include more physical machines to scale up the application
- Introduce other technologies to make the application more scalable (*e.g.* Apache Spark, Apache Flink, etc.)

## How can PII be recovered later on?
- Use the same key to decrypt the PII data

## What are the assumptions you made?
- The general format of message will not change. The only thing that could change is the body of the message.
- The generated message that is not in the standard format is useless and can be ignored
- The version of application like `a.b.c/a.b` could be converted to an integer number `a*pow(2,8) + b*pow(2,4) + c` since the version number is not too large and this approach will fit the value into the integer type in the database
