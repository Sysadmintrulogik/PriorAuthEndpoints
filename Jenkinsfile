pipeline {
    agent { label 'GPUmaster' }

    environment {
        VAULT_URL = 'http://172.210.25.139:8200'
    }

    parameters {
        string(name: 'BRANCH_NAME', defaultValue: 'revamp/app', description: 'Branch to build')
    }

    stages{
        
        stage('Checkout') {
            steps {
                script {
                    echo "Checking out branch: ${params.BRANCH_NAME}"
                    checkout([$class: 'GitSCM',
                        branches: [[name: "*/${params.BRANCH_NAME}"]],
                        userRemoteConfigs: [[
                            url: 'https://github.com/Sysadmintrulogik/PriorAuthEndpoints.git',
                            credentialsId: 'd3924fd8-5a0b-4583-89d3-3f0b560104ed'
                        ]]
                    ])
                }
            }
        }
        
        stage('Abort Previous Builds') {
            steps {
                script {
                    def jobName = env.JOB_NAME
                    def currentBuildNumber = env.BUILD_NUMBER.toInteger()
                    def job = Jenkins.instance.getItemByFullName(jobName)
                    if (job) {
                        def buildsToAbort = job.builds.findAll { build ->
                            build.isBuilding() && build.number != currentBuildNumber
                        }
         
                        buildsToAbort.each { build ->
                            echo "Aborting build #${build.number}"
                            build.doStop()
                        }
                    }
                }
            }
        }
 
        stage('Make entrypoint executable') {
            steps {
                script {
                    sh '''
                        #!/bin/bash
                        set -e
                        chmod +x ./entrypoint.sh  # Make entrypoint executable
                    '''
                }
            }
        }

        stage('Fetch from Vault'){
            steps{
                withVault(configuration: [
                    vaultCredentialId: 'vault-token',
                    vaultUrl: "${VAULT_URL}",
                ], vaultSecrets: [
                    [
                        path: 'jenkinskv/python/postgresDB',
                        secretValues: [
                            [envVar: 'DB_USERNAME',vaultKey: 'DB_USERNAME'],
                            [envVar: 'DB_PASSWORD',vaultKey: 'DB_PASSWORD'],
                            [envVar: 'DB_SERVER_NAME',vaultKey: 'DB_SERVER'],
                            [envVar: 'DATABASE_NAME',vaultKey: 'DATABASE_NAME'],
                            [envVar: 'DB_PORT',vaultKey: 'DB_PORT']
                        ]
                    ]
                ]) {
                    script {
                        // Use the environment variables set by the withVault step
                        def dbUsername = env.DB_USERNAME
                        def dbPassword = env.DB_PASSWORD
                        def dbServerName = env.DB_SERVER_NAME
                        def dbName = env.DATABASE_NAME
                        def dbPort = env.DB_PORT

                        // Write the secrets to application-dev.properties
                        sh """
                            echo "" >> .env
                            echo "DB_PORT=${dbPort}" >> .env
                            echo "DB_USERNAME=${dbUsername}" >> .env
                            echo "DB_PASSWORD=${dbPassword}" >> .env
                            echo "DB_SERVER_NAME=${dbServerName}" >> .env
                            echo "DATABASE_NAME=${dbName}" >> .env
                        """
                    }
                }
            }
        }
 
        stage('Run Flask App') {
            steps {
                script {
                    // Build the Docker images without cache
                    sh '''
                        set -e
                        whoami
                        docker compose build
                    '''

                    try {
                        sh '''
                            docker compose down --remove-orphans
                        '''
                    } catch (Exception e) {
                        echo "Error during container down: ${e.message}"
                    }

                    try {
                        sh '''
                            docker container stop trulogik-prior-auth-endpoints-revamp-app
                        '''
                    } catch (Exception e) {
                        echo "Error during container stop: ${e.message}"
                    }

                    try {
                        sh '''
                            docker container prune -f
                        '''
                    } catch (Exception e) {
                        echo "Error during container prune: ${e.message}"
                    }

                    sh '''
                        set -e
                        docker compose up -d
                    '''
                }
            }
        }
    }
 
    post {
        always {
            // Clean up the workspace
            cleanWs()
        }
        success {
            echo 'Deployment on VM successful!'
        }
        failure {
            echo 'Deployment failed!'
        }
    }
}
 
// Function to load environment variables from a file using readFile
def loadEnvFile(filePath) {
    def envVars = []
    try {
        def fileContent = readFile filePath
        fileContent.split('\n').each { line ->
            line = line.trim()
            if (line && !line.startsWith('#')) {
                def (key, value) = line.split('=', 2)
                envVars << "${key}=${value}"
            }
        }
    } catch (Exception e) {
        echo "Error reading .env file: ${e.message}"
        return null
    }
    return envVars
}
