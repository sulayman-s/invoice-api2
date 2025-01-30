#!/usr/bin/env groovy

def label = "invoice-api-${UUID.randomUUID().toString()}"
podTemplate(label: label, yaml: """
    apiVersion: v1
    kind: Pod
    metadata:
        name: ${label}
        annotations:
            container.apparmor.security.beta.kubernetes.io/${label}: unconfined
    labels:
        app: ${label}
    spec:
      containers:
      - name: ${label}
        image: moby/buildkit:v0.9.2-rootless
        imagePullPolicy: IfNotPresent
        command:
        - cat
        tty: true
      - name: kubectl
        image: lachlanevenson/k8s-kubectl:v1.21.10
        imagePullPolicy: IfNotPresent
        command:
        - cat
        tty: true
      nodeSelector:
        workload: batch
      serviceAccountName: invoice-api
    """,
    slaveConnectTimeout: 3600
  ) {
    node(label) {
        stage('setup') {
            git url: 'https://ds1.capetown.gov.za/ds_gitlab/OPM/invoice-data-processing.git', branch: env.BRANCH_NAME, credentialsId: 'jenkins-user'
        }
        stage('docker-build') {
            retry(10) {
                container(label) {
                    withCredentials([usernamePassword(credentialsId: 'opm-data-proxy-user', passwordVariable: 'OPM_DATA_PASSWORD', usernameVariable: 'OPM_DATA_USER'),
                                     usernamePassword(credentialsId: 'docker-user', passwordVariable: 'DOCKER_PASS', usernameVariable: 'DOCKER_USER')]) {
                        sh '''
                        export SAFE_BRANCH_NAME=$(echo $BRANCH_NAME | sed 's#/#-#g')
                        chmod a+x ./bin/buildkit-docker.sh
                        ./bin/buildkit-docker.sh "${OPM_DATA_USER}" "${OPM_DATA_PASSWORD}" \\
                                                 "${DOCKER_USER}" "${DOCKER_PASS}" \\
                                                 "${PWD}" \\
                                                 "docker.io/cityofcapetown/invoice-api-backend:${SAFE_BRANCH_NAME}" \\
                                                 "true"
                        sleep 60
                        '''
                    }
                    updateGitlabCommitStatus name: 'image-build', state: 'success'
                }
            }
        }
        stage('k8s-deploy') {
            if (env.BRANCH_NAME == 'main') {
                container('kubectl') {
                    sh '''
                    kubectl apply -f ${PWD}/resources/invoice-api.yaml
                    kubectl rollout restart statefulset -n invoice-api-dev invoice-api-backend-dev
                    kubectl rollout status statefulset -n invoice-api-dev invoice-api-backend-dev --timeout=900s
                    '''
                    updateGitlabCommitStatus name: 'deploy', state: 'success'
                }
            } else {
                container('kubectl') {
                    sh '''
                    kubectl apply -f ${PWD}/resources/invoice-api-dev.yaml
                    kubectl rollout restart statefulset -n invoice-api-dev invoice-api-backend-dev
                    kubectl rollout status statefulset -n invoice-api-dev invoice-api-backend-dev --timeout=900s
                    '''
                    updateGitlabCommitStatus name: 'deploy', state: 'success'
                }
            }
        }
    }
}
