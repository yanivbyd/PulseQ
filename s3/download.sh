#!/bin/bash
aws s3 sync s3://pulseq-inputs/ s3/pulseq-inputs/ --region eu-west-1
aws s3 sync s3://pulseq/ s3/pulseq/ --region eu-west-1
