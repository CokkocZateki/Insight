import datetime
import time

from .base_objects import *
from . import characters, corporations, alliances, types, systems, constellations, regions
import requests
import traceback
import InsightLogger


class name_resolve(name_only):
    @classmethod
    def post_url(cls):
        return "https://esi.evetech.net/v3/universe/names/?datasource=tranquility"

    @classmethod
    def __get_objects_with_missing_names(cls, service_module, exclude_nonentity=False, exclude_entity=False):
        __missing_objects = []
        if not exclude_nonentity:
            __missing_objects += types.Types.missing_name_objects(service_module, cls.get_remaining_limit(len(__missing_objects)))
            __missing_objects += systems.Systems.missing_name_objects(service_module, cls.get_remaining_limit(len(__missing_objects)))
            __missing_objects += constellations.Constellations.missing_name_objects(service_module, cls.get_remaining_limit(len(__missing_objects)))
            __missing_objects += regions.Regions.missing_name_objects(service_module, cls.get_remaining_limit(len(__missing_objects)))
        if not exclude_entity:
            __missing_objects += alliances.Alliances.missing_name_objects(service_module, cls.get_remaining_limit(len(__missing_objects)))
            __missing_objects += corporations.Corporations.missing_name_objects(service_module, cls.get_remaining_limit(len(__missing_objects)))
            __missing_objects += characters.Characters.missing_name_objects(service_module, cls.get_remaining_limit(len(__missing_objects)))
        return __missing_objects

    @classmethod
    def missing_count(cls, service_module, exclude_nonentity=False, exclude_entity=False)->int:
        db = service_module.get_session()
        try:
            return len(cls.__get_objects_with_missing_names(service_module, exclude_nonentity=exclude_nonentity, exclude_entity=exclude_entity))
        except Exception as ex:
            print(ex)
            return -1
        finally:
            db.close()

    @classmethod
    def commit_batch_rows_max(cls):
        return 50000

    @classmethod
    def get_remaining_limit(cls, missing_object_len):
        if missing_object_len >= cls.commit_batch_rows_max():
            return 0
        else:
            return cls.commit_batch_rows_max() - missing_object_len

    @classmethod
    def _get_expired_ids(cls, error_dict, minutes_timeout):
        """returns a list of error id dictionaries to be rechecked after their cooldown period"""
        current_time = datetime.datetime.utcnow()
        return_items = []
        for error_id, last_check in error_dict.items():
            if current_time >= last_check + datetime.timedelta(minutes=minutes_timeout):
                return_items.append(error_id)
        return return_items

    @classmethod
    def api_mass_name_resolve(cls, service_module, error_ids_404={}, error_ids_non404={}, exclude_nonentity=False,
                              exclude_entity=False):
        lg = InsightLogger.InsightLogger.get_logger('ZK.names', 'ZK.log', child=True)

        ids_404_pending_recheck = []
        for i in cls._get_expired_ids(error_dict=error_ids_404, minutes_timeout=90):
            ids_404_pending_recheck.append(i) # add to list
            error_ids_404.pop(i) #remove from return result
        for i in cls._get_expired_ids(error_dict=error_ids_non404, minutes_timeout=15):
            error_ids_non404.pop(i) # remove from return result
        error_count = 0
        while True:
            if error_count >= 3: #infinite loop prevention
                while True: # if there are errors we need to prevent poisoning the next batch by adding the recheck 404 ids back to the return result
                    try:
                        error_ids_404[ids_404_pending_recheck.pop()] = datetime.datetime.utcnow() - datetime.timedelta(minutes=90) # set to be immediate expire in next batch
                    except IndexError:
                        break
                break
            db: Session = service_module.get_session()
            try:
                missing_object_dict = {}
                for row in cls.__get_objects_with_missing_names(service_module, exclude_nonentity=exclude_nonentity, exclude_entity=exclude_entity):
                    missing_object_dict[row.get_id()] = row
                id_keys = list(set(list(missing_object_dict.keys())) - set(list(error_ids_404.keys()) + list(ids_404_pending_recheck) + list(error_ids_non404.keys())))
                commit_pending_buffer = 0
                completed_count = 0
                if len(id_keys) == 0 and len(ids_404_pending_recheck) == 0:
                    break
                elif len(ids_404_pending_recheck) > 0: # start processing ids in 404 errors one by one to not mark entire batch as dirty
                    try:
                        id_keys = [ids_404_pending_recheck.pop()]
                    except IndexError:
                        break
                    api_chunk_size = 1
                    processing_404 = True
                else:
                    api_chunk_size = cls.missing_id_chunk_size()
                    processing_404 = False
                if len(id_keys) >= cls.missing_id_chunk_size():
                    print("Mass name resolve needs to resolve {} names. Total current error 404s: {}, Total current error non404s: {}".
                          format(len(id_keys), len(error_ids_404.keys()), len(error_ids_non404.keys())))
                for id_list in cls.split_lists(id_keys, api_chunk_size):
                    completed_count += len(id_list)
                    lg.info('Processing name chunk of size {} from {}/{} total missing names.'.format(len(id_list),
                                                                                                      completed_count,
                                                                                                      len(id_keys)))
                    try:
                        response = requests.post(url=cls.post_url(), headers=service_module.get_headers(lib_requests=True),
                                                 json=id_list, timeout=3)
                        if response.status_code == 200:
                            commit_pending_buffer += len(id_list)
                            for search_result in response.json():
                                selected_item = missing_object_dict.get(search_result.get('id'))
                                if selected_item is not None:
                                    selected_item.set_name(search_result.get('name'))
                            if commit_pending_buffer >= cls.commit_batch_rows_max():
                                db.commit()
                                print("Completed batch of {} names.".format(commit_pending_buffer))
                                commit_pending_buffer = 0
                        elif response.status_code == 404:
                            lg.warning('Response {} Headers: {} IDs: {}'.format(response.status_code,
                                                                                response.headers, str(id_list)))
                            if processing_404:
                                commit_pending_buffer += 1
                                sel_id = id_list[0]
                                selected_item = missing_object_dict.get(sel_id) # we are calling one by one, no batch
                                selected_item.set_name("!!UNKNOWN NAME!!")
                                err_str = "Type: {} ID: {} is still returning response 404s on retry. Setting to !!UNKNOWN NAME!!".format(type(selected_item),sel_id)
                                print(err_str)
                                lg.error(err_str)
                            else:
                                for i in id_list:
                                    error_ids_404[i] = datetime.datetime.utcnow()
                                error_count += 1
                        elif response.status_code == 420:
                            lg.warning('Response {} Headers: {} IDs: {}'.format(response.status_code,
                                                                                response.headers, str(id_list)))
                            for i in id_list:
                                error_ids_non404[i] = datetime.datetime.utcnow()
                            error_count += 1
                            time.sleep(60)
                        elif 400 <= response.status_code < 600:
                            lg.warning('Response {} Headers: {} IDs: {}'.format(response.status_code,
                                                                                response.headers, str(id_list)))
                            for i in id_list:
                                error_ids_non404[i] = datetime.datetime.utcnow()
                            error_count += 1
                        else:
                            lg.warning('Response {} Headers: {} IDs: {}'.format(response.status_code,
                                                                                response.headers, str(id_list)))
                            for i in id_list:
                                error_ids_non404[i] = datetime.datetime.utcnow()
                            error_count += 1
                    except requests.exceptions.Timeout:
                        lg.info('Timeout.')
                        for i in id_list:
                            error_ids_non404[i] = datetime.datetime.utcnow()
                        error_count += 1
                    except Exception as ex:
                        lg.exception(ex)
                        lg.info('Error IDs: {}'.format(str(id_list)))
                        print('Error: {} when resolving names.'.format(ex))
                        for i in id_list:
                            error_ids_non404[i] = datetime.datetime.utcnow()
                        error_count += 1
                if commit_pending_buffer > 0:
                    db.commit()
                    if len(id_keys) >= cls.missing_id_chunk_size():
                        print("Completed batch of {} names.".format(commit_pending_buffer))
            except Exception as ex:
                print(ex)
                traceback.print_exc()
                error_count += 1
            finally:
                db.close()
