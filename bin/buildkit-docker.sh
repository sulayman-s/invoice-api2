#!/usr/bin/env sh
echo "test 0"
OPM_DATA_USER=$1
OPM_DATA_PASSWORD=$2
DOCKER_USER=$3
DOCKER_PASS=$4
CONTEXT_PATH=$5
IMAGE_TAG=$6
PUSH=$7
echo "test 1"
# Setting up proxy env variables
export http_proxy=http://${OPM_DATA_USER}:${OPM_DATA_PASSWORD}@internet.capetown.gov.za:8080
export https_proxy=http://${OPM_DATA_USER}:${OPM_DATA_PASSWORD}@internet.capetown.gov.za:8080
export HTTP_PROXY=http://${OPM_DATA_USER}:${OPM_DATA_PASSWORD}@internet.capetown.gov.za:8080
export HTTPS_PROXY=http://${OPM_DATA_USER}:${OPM_DATA_PASSWORD}@internet.capetown.gov.za:8080
export no_proxy=datascience.capetown.gov.za,lake.capetown.gov.za,ds1.capetown.gov.za,ds2.capetown.gov.za
export NO_PROXY=datascience.capetown.gov.za,lake.capetown.gov.za,ds1.capetown.gov.za,ds2.capetown.gov.za

# Setting up config file
export DOCKER_CONFIG="${PWD}/.docker"
mkdir -p ${DOCKER_CONFIG}
export DOCKER_CONFIG_FILE="${DOCKER_CONFIG}/config.json"
echo "writing to file"
echo '{' > ${DOCKER_CONFIG_FILE}

# Setting up docker auth
export BASE64_USER_PASS=$(echo -n "${DOCKER_USER}:${DOCKER_PASS}" | base64)
echo '"auths": {"https://index.docker.io/v1/": {"auth": "'${BASE64_USER_PASS}'"}},' >> ${DOCKER_CONFIG_FILE}

# Setting up docker proxy
echo "\"proxies\": {\"default\": { \"http_proxy\": \"${http_proxy}\", \"https_proxy\": \"${http_proxy}\", \"no_proxy\": \"${no_proxy}\"}}" >> ${DOCKER_CONFIG_FILE}

echo '}' >> ${DOCKER_CONFIG_FILE}
echo "write to file"
# Getting output of dockerfile
echo "Contents of ${DOCKER_CONFIG_FILE}"
cat ${DOCKER_CONFIG_FILE}

# Here we go!
export BUILDKITD_FLAGS=--oci-worker-no-process-sandbox
echo "building from "${CONTEXT_PATH}", with IMAGE_TAG="${IMAGE_TAG}" and PUSH="${PUSH}""
buildctl-daemonless.sh build --frontend dockerfile.v0 \
                             --local context="${CONTEXT_PATH}" \
                             --local dockerfile="${CONTEXT_PATH}" \
                             --opt build-arg:http_proxy="${http_proxy}" \
                             --opt build-arg:https_proxy="${http_proxy}" \
                             --opt build-arg:no_proxy="${no_proxy}" \
                             --opt build-arg:HTTP_PROXY="${http_proxy}" \
                             --opt build-arg:HTTPS_PROXY="${http_proxy}" \
                             --opt build-arg:NO_PROXY="${no_proxy}" \
                             --export-cache type=inline \
                             --import-cache type=registry,ref="${IMAGE_TAG}" \
                             --output type=image,name="${IMAGE_TAG}",push="${PUSH}"

exit $?
