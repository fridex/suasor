import numpy as np
import pandas as pd
import sklearn
import scipy
from scipy.sparse import coo_matrix
from implicit.als import AlternatingLeastSquares
import json
import os
import sys


query = """
WITH stars AS (
     SELECT actor.login AS user, repo.name AS repo
     FROM githubarchive.month.201706
     WHERE type="WatchEvent"
),
repositories_stars AS (
     SELECT repo, COUNT(*) as c FROM stars GROUP BY repo
     ORDER BY c DESC
     LIMIT 1000
),
users_stars AS (
    SELECT user, COUNT(*) as c FROM  stars
    WHERE repo IN (SELECT repo FROM repositories_stars)
    GROUP BY user HAVING c > 10 AND C < 100
    LIMIT 10000
)
SELECT user, repo FROM stars
WHERE repo IN (SELECT repo FROM repositories_stars)
AND user IN (SELECT user FROM users_stars)
"""

gc_svc_account = {
  "type": "service_account",
  "project_id": "suasor-184008",
  "private_key_id": "<TBD>",
  "private_key": "<TBD>",
  "client_email": "webquery@suasor-184008.iam.gserviceaccount.com",
  "client_id": "103981968423963988522",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://accounts.google.com/o/oauth2/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/webquery%40suasor-184008.iam.gserviceaccount.com"
}

def main(params):
    # check for mandatory params
    if not 'reference_repo' in params:
        return {'error' : 'Mandatory param reference_repo not present'}
    reference_repo = params['reference_repo']
    print('reference_repo', reference_repo)

    # get data
    print('read GBQ data')
    gc_svc_account['private_key_id'] = params['GC_SVC_PRIVATE_KEY_ID']
    gc_svc_account['private_key'] = params['GC_SVC_PRIVATE_KEY']
    data = pd.io.gbq.read_gbq(query, dialect="standard", project_id=gc_svc_account['project_id'], private_key=json.dumps(gc_svc_account))

    # map each repo and user to a unique numeric value
    data['user'] = data['user'].astype("category")
    data['repo'] = data['repo'].astype("category")

    # dictionaries to translate names to ids and vice-versa
    repos = dict(enumerate(data['repo'].cat.categories))
    repo_ids = {r: i for i, r in repos.items()}

    if reference_repo not in repo_ids:
        return {"message" : "No result. Reference repo not in training set."}
    
    # create a sparse matrix of all the users/repos
    stars = coo_matrix((np.ones(data.shape[0]),
                        (data['repo'].cat.codes.copy(),
                        data['user'].cat.codes.copy())))

    # train model
    print('training model')
    model = AlternatingLeastSquares(factors=50,
                                regularization=0.01,
                                dtype=np.float64,
                                iterations=50)
    confidence = 40
    model.fit(confidence * stars)
 
    similar_ids = model.similar_items(repo_ids[reference_repo])
    print('found ', len(similar_ids), ' similar repos')

    result = []
    for x in range(1, len(similar_ids)):
        result.append(repos[similar_ids[x][0]])
    
    return {'reference_repo': reference_repo, 'similar_repos':result, 'errror' : ''}


# for local testing
if __name__ == "__main__":
    params = {}
    params['GC_SVC_PRIVATE_KEY'] = bytes(os.environ['GC_SVC_PRIVATE_KEY'], "utf-8").decode('unicode_escape')
    params['GC_SVC_PRIVATE_KEY_ID'] = bytes(os.environ['GC_SVC_PRIVATE_KEY_ID'], "utf-8").decode('unicode_escape')
    params['reference_repo'] = sys.argv[1]
    print(main(params))
